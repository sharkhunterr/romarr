"""DAT-sources management — /api/v3/dat-source.

Two surfaces in one router:

- **Cache summary** (read-only, grouped by ``DatEntry.source``):
  the ``GET /summary`` endpoint surfaces the ingested-entry roll-up
  the Settings → DAT Sources page used to show pre-slice 443.
- **Source CRUD** (slice 443): CREATE / LIST / DELETE rows in the
  new ``dat_source`` table plus per-row ``/refresh`` and a
  ``/refresh-all`` shortcut that triggers the existing
  :class:`DatUpdateRunner` against every enabled row.

The runner downloads each configured URL, hands the body to
:meth:`DatManager.ingest`, and records the outcome
(``last_refresh_status`` / ``last_refresh_error`` /
``last_entry_count`` / ``last_refresh_at``) on the source row.
Per-source failures don't abort the loop — operators see them
inline on the next list call.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import DatEntry, DatSource, Platform
from romarr.identification.dat.manager import DatManager

_log = logging.getLogger(__name__)


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatSourceSummary(_Base):
    """Read-only summary of ingested entries grouped by DAT
    authority (no-intro / redump / …). The Settings page renders
    this alongside the per-source rows so operators see both:
    'I asked for these 4 URLs' AND 'they produced 27 000 entries
    last refresh'."""

    source: str
    entry_count: int
    platform_count: int
    latest_updated_at: datetime | None


_AuthoritySource = Literal[
    "no-intro", "redump", "tosec", "goodtools", "hasheous", "playmatch", "custom"
]
_RefreshStatus = Literal["ok", "failed", "running"]


class DatSourceRead(_Base):
    id: int
    name: str
    url: str
    source: _AuthoritySource
    platform_id: int
    platform_slug: str | None = None
    platform_name: str | None = None
    enabled: bool
    last_refresh_at: datetime | None
    last_refresh_status: _RefreshStatus | None
    last_refresh_error: str | None
    last_entry_count: int | None
    created_at: datetime
    updated_at: datetime


class DatSourceCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    url: Annotated[str, Field(min_length=1, max_length=1024)]
    source: _AuthoritySource
    platform_id: int
    enabled: bool = True


class DatSourceUpdate(_Base):
    name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=128)
    ] = None
    url: Annotated[
        str | None, Field(default=None, min_length=1, max_length=1024)
    ] = None
    enabled: bool | None = None


class RefreshOutcome(_Base):
    """Per-source result returned by /refresh + /refresh-all."""

    id: int
    name: str
    status: _RefreshStatus
    entries_ingested: int | None = None
    error: str | None = None


router = APIRouter(prefix="/api/v3/dat-source", tags=["DAT Sources"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MAX_DAT_BYTES = 64 * 1024 * 1024


def _to_read(row: DatSource, platform: Platform | None = None) -> DatSourceRead:
    return DatSourceRead.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "url": row.url,
            "source": row.source,
            "platform_id": row.platform_id,
            "platform_slug": platform.slug if platform else None,
            "platform_name": platform.name if platform else None,
            "enabled": row.enabled,
            "last_refresh_at": row.last_refresh_at,
            "last_refresh_status": row.last_refresh_status,
            "last_refresh_error": row.last_refresh_error,
            "last_entry_count": row.last_entry_count,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


async def _refresh_one(
    *, session: AsyncSession, row: DatSource, platform: Platform
) -> RefreshOutcome:
    """Download + ingest one DAT source, updating the row's
    ``last_refresh_*`` fields. Errors are caught + recorded; the
    caller decides whether to abort the batch (we never re-raise)."""
    row.last_refresh_status = "running"
    row.last_refresh_error = None
    await session.commit()

    bytes_body: bytes | None = None
    error_msg: str | None = None
    try:
        async with httpx.AsyncClient(
            timeout=60.0, follow_redirects=True
        ) as client:
            resp = await client.get(row.url)
            if resp.status_code >= 400:
                error_msg = (
                    f"upstream {resp.status_code} fetching {row.url}: "
                    f"{resp.text[:200]}"
                )
            elif len(resp.content) > _MAX_DAT_BYTES:
                error_msg = (
                    f"upstream returned {len(resp.content)} bytes "
                    f"(> {_MAX_DAT_BYTES} cap)"
                )
            else:
                bytes_body = resp.content
    except httpx.HTTPError as exc:
        error_msg = f"network: {exc!s}"
    except Exception as exc:  # noqa: BLE001 — log + surface, don't kill loop
        error_msg = f"unexpected: {exc!s}"

    # Many DAT mirrors (e.g. redump.org/datfile/{slug}/) wrap the
    # Logiqx XML inside a single-entry zip. Transparently extract
    # the first .dat / .xml member so operators can paste the
    # direct-download URL without an unzipping step.
    if bytes_body is not None and bytes_body[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(bytes_body)) as zf:
                inner_name = next(
                    (
                        n
                        for n in zf.namelist()
                        if n.lower().endswith((".dat", ".xml"))
                    ),
                    None,
                )
                if inner_name is None:
                    error_msg = (
                        f"zip from {row.url} has no .dat/.xml member "
                        f"(contents: {zf.namelist()[:5]})"
                    )
                    bytes_body = None
                else:
                    bytes_body = zf.read(inner_name)
                    if len(bytes_body) > _MAX_DAT_BYTES:
                        error_msg = (
                            f"unzipped {inner_name} is {len(bytes_body)} "
                            f"bytes (> {_MAX_DAT_BYTES} cap)"
                        )
                        bytes_body = None
        except zipfile.BadZipFile as exc:
            error_msg = f"bad zip: {exc!s}"
            bytes_body = None

    now = datetime.now(UTC)
    if bytes_body is None:
        row.last_refresh_status = "failed"
        row.last_refresh_error = (error_msg or "unknown")[:500]
        row.last_refresh_at = now
        await session.commit()
        return RefreshOutcome(
            id=row.id, name=row.name, status="failed", error=error_msg
        )

    try:
        manager = DatManager(session)
        ingest_stats = await manager.ingest(
            dat_bytes=bytes_body,
            platform_id=row.platform_id,
            source=row.source,
        )
    except Exception as exc:  # noqa: BLE001
        row.last_refresh_status = "failed"
        row.last_refresh_error = f"ingest: {exc!s}"[:500]
        row.last_refresh_at = now
        await session.commit()
        _log.exception(
            "dat_source.refresh.ingest_failed id=%s url=%s", row.id, row.url
        )
        return RefreshOutcome(
            id=row.id, name=row.name, status="failed", error=str(exc)
        )

    # On an idempotent re-fetch ``inserted=0`` doesn't reflect the
    # actual rows in dat_entry — surface the real per-source row
    # count so the UI doesn't appear to lose entries.
    actual_count = (
        await session.execute(
            select(func.count(DatEntry.id)).where(
                DatEntry.platform_id == row.platform_id,
                DatEntry.source == row.source,
                DatEntry.dat_contents_hash == ingest_stats.contents_hash,
            )
        )
    ).scalar_one()

    row.last_refresh_status = "ok"
    row.last_refresh_error = None
    row.last_entry_count = int(actual_count)
    row.last_refresh_at = now
    await session.commit()
    return RefreshOutcome(
        id=row.id,
        name=row.name,
        status="ok",
        entries_ingested=int(actual_count),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[DatSourceSummary],
    summary="DAT cache summary grouped by source (any authenticated user).",
)
async def summary(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DatSourceSummary]:
    """One row per distinct ``DatEntry.source``, with entry count
    + platform count + latest updated_at. The Settings page pairs
    this with the per-row source list below."""
    rows = (
        await db.execute(
            select(
                DatEntry.source,
                func.count(DatEntry.id).label("entry_count"),
                func.count(distinct(DatEntry.platform_id)).label(
                    "platform_count"
                ),
                func.max(DatEntry.updated_at).label("latest_updated_at"),
            )
            .group_by(DatEntry.source)
            .order_by(DatEntry.source.asc())
        )
    ).all()

    return [
        DatSourceSummary(
            source=row.source,
            entry_count=int(row.entry_count),
            platform_count=int(row.platform_count),
            latest_updated_at=row.latest_updated_at,
        )
        for row in rows
    ]


@router.get(
    "/sources",
    response_model=list[DatSourceRead],
    summary="List configured DAT source URLs (any authenticated user).",
)
async def list_sources(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DatSourceRead]:
    rows = (
        await db.execute(
            select(DatSource, Platform)
            .join(Platform, Platform.id == DatSource.platform_id)
            .order_by(Platform.name.asc(), DatSource.source.asc())
        )
    ).all()
    return [_to_read(src, plat) for src, plat in rows]


@router.post(
    "/sources",
    response_model=DatSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new DAT source URL (admin only).",
)
async def create_source(
    payload: DatSourceCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatSourceRead:
    platform = (
        await db.execute(
            select(Platform).where(Platform.id == payload.platform_id)
        )
    ).scalar_one_or_none()
    if platform is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
            },
        )
    row = DatSource(
        name=payload.name,
        url=payload.url,
        source=payload.source,
        platform_id=payload.platform_id,
        enabled=payload.enabled,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_dat_source",
                "errorCode": "duplicate",
                "details": (
                    f"a {payload.source!r} source already exists for "
                    f"platform_id={payload.platform_id}"
                ),
            },
        ) from exc
    await db.refresh(row)
    return _to_read(row, platform)


@router.put(
    "/sources/{source_id}",
    response_model=DatSourceRead,
    summary="Update a DAT source (admin only).",
)
async def update_source(
    source_id: int,
    payload: DatSourceUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatSourceRead:
    row = (
        await db.execute(select(DatSource).where(DatSource.id == source_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "dat_source_not_found", "errorCode": "not_found"},
        )
    fields = payload.model_dump(exclude_unset=True)
    for key in ("name", "url", "enabled"):
        if key in fields and fields[key] is not None:
            setattr(row, key, fields[key])
    await db.commit()
    await db.refresh(row)
    platform = (
        await db.execute(select(Platform).where(Platform.id == row.platform_id))
    ).scalar_one_or_none()
    return _to_read(row, platform)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a DAT source (admin only). Ingested DatEntry rows kept.",
)
async def delete_source(
    source_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await db.execute(delete(DatSource).where(DatSource.id == source_id))
    await db.commit()


@router.post(
    "/sources/{source_id}/refresh",
    response_model=RefreshOutcome,
    summary="Re-fetch + re-ingest one DAT source (admin only).",
)
async def refresh_source(
    source_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshOutcome:
    row = (
        await db.execute(select(DatSource).where(DatSource.id == source_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "dat_source_not_found", "errorCode": "not_found"},
        )
    platform = (
        await db.execute(select(Platform).where(Platform.id == row.platform_id))
    ).scalar_one()
    return await _refresh_one(session=db, row=row, platform=platform)


@router.post(
    "/sources/refresh-all",
    response_model=list[RefreshOutcome],
    summary="Re-fetch + re-ingest every enabled DAT source (admin only).",
)
async def refresh_all(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RefreshOutcome]:
    rows = (
        await db.execute(
            select(DatSource, Platform)
            .join(Platform, Platform.id == DatSource.platform_id)
            .where(DatSource.enabled.is_(True))
            .order_by(Platform.name.asc())
        )
    ).all()
    outcomes: list[RefreshOutcome] = []
    for row, platform in rows:
        outcomes.append(
            await _refresh_one(session=db, row=row, platform=platform)
        )
    return outcomes
