"""Pack-source endpoints — `/api/v3/rom/platform-pack-source/*`.

  - GET    /api/v3/rom/platform-pack-source              — list
  - POST   /api/v3/rom/platform-pack-source              — create
  - PATCH  /api/v3/rom/platform-pack-source/{id}         — toggle enabled
  - DELETE /api/v3/rom/platform-pack-source/{id}         — remove
  - POST   /api/v3/rom/platform-pack-source/{id}/sync    — fetch + apply

Admin-only. Sync uses the same :func:`ingest_pack` path as the
manual multipart upload — the only difference is where the YAML
bytes come from.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.api.dependencies import get_db, get_sessionmaker, require_admin
from romarr.auth import Principal
from romarr.platform_packs import (
    IngestSource,
    PackValidationError,
    PackVersionConflictError,
    ingest_pack,
)
from romarr.platform_packs.models import PackSource
from romarr.platform_packs.remote import (
    RemotePackError,
    classify_url,
    fetch_from_source,
)

router = APIRouter(
    prefix="/api/v3/rom/platform-pack-source",
    tags=["Platform Packs"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class SourceSummary(_Base):
    id: int
    name: str
    url: str
    kind: str
    enabled: bool
    last_synced_at: datetime | None
    last_status: str | None
    last_error: str | None
    last_applied_count: int


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=128)
    url: HttpUrl
    kind: str | None = Field(
        None,
        description="Override the auto-detected kind ('raw' | 'github_dir'). "
        "Leave null to let the server guess from the URL shape.",
    )


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool | None = None
    name: str | None = Field(None, min_length=1, max_length=128)


class SyncItemOutcome(BaseModel):
    """One YAML body processed during a sync run."""

    filename: str
    source_url: str
    outcome: str  # "applied", "skipped", "failed"
    pack_version: str | None = None
    error: str | None = None


class SyncResult(BaseModel):
    source_id: int
    fetched_at: datetime
    status: str  # "ok", "partial", "error"
    items: list[SyncItemOutcome] = Field(default_factory=list)
    applied_count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_summary(row: PackSource) -> SourceSummary:
    return SourceSummary.model_validate(row)


async def _get_or_404(db: AsyncSession, source_id: int) -> PackSource:
    row = (
        await db.execute(select(PackSource).where(PackSource.id == source_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"pack source {source_id} not found",
                "errorCode": "not_found",
            },
        )
    return row


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[SourceSummary],
    summary="List every registered pack source (admin).",
)
async def list_sources(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SourceSummary]:
    rows = (
        (await db.execute(select(PackSource).order_by(PackSource.id.desc())))
        .scalars()
        .all()
    )
    return [_to_summary(r) for r in rows]


@router.post(
    "",
    response_model=SourceSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new remote pack source (admin).",
)
async def create_source(
    payload: SourceCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceSummary:
    url_s = str(payload.url)
    kind = payload.kind or classify_url(url_s)
    if kind not in ("raw", "github_dir"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": f"unknown kind {kind!r} (want 'raw' or 'github_dir')",
                "errorCode": "invalid_kind",
            },
        )

    # Dedup by name — 409 is friendlier than a raw IntegrityError.
    existing = (
        await db.execute(select(PackSource).where(PackSource.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": f"pack source named {payload.name!r} already exists",
                "errorCode": "duplicate_name",
            },
        )

    row = PackSource(name=payload.name, url=url_s, kind=kind, enabled=True)
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return _to_summary(row)


# ---------------------------------------------------------------------------
# Update + delete
# ---------------------------------------------------------------------------


@router.patch(
    "/{source_id}",
    response_model=SourceSummary,
    summary="Toggle enabled or rename a source (admin).",
)
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceSummary:
    row = await _get_or_404(db, source_id)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.name is not None and payload.name != row.name:
        clash = (
            await db.execute(
                select(PackSource).where(
                    PackSource.name == payload.name, PackSource.id != source_id
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "errorMessage": f"pack source named {payload.name!r} already exists",
                    "errorCode": "duplicate_name",
                },
            )
        row.name = payload.name
    await db.commit()
    await db.refresh(row)
    return _to_summary(row)


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a source (admin). Does not un-apply the packs it fed.",
)
async def delete_source(
    source_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _get_or_404(db, source_id)
    await db.execute(delete(PackSource).where(PackSource.id == source_id))
    await db.commit()


# ---------------------------------------------------------------------------
# Sync-now
# ---------------------------------------------------------------------------


@router.post(
    "/{source_id}/sync",
    response_model=SyncResult,
    summary="Fetch and ingest every pack the source advertises (admin).",
)
async def sync_source(
    source_id: int,
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sm: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> SyncResult:
    row = await _get_or_404(db, source_id)
    if not row.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "source is disabled — enable it before syncing",
                "errorCode": "source_disabled",
            },
        )

    fetched_at = datetime.now(UTC)
    items: list[SyncItemOutcome] = []
    applied_count = 0

    try:
        yamls = await fetch_from_source(row.url, row.kind)
    except RemotePackError as e:
        row.last_synced_at = fetched_at
        row.last_status = "error"
        row.last_error = str(e)[:1024]
        row.last_applied_count = 0
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"errorMessage": str(e), "errorCode": "remote_fetch_failed"},
        ) from e

    if not yamls:
        row.last_synced_at = fetched_at
        row.last_status = "ok"
        row.last_error = "no YAML files found at source"
        row.last_applied_count = 0
        await db.commit()
        return SyncResult(
            source_id=source_id,
            fetched_at=fetched_at,
            status="ok",
            items=[],
            applied_count=0,
        )

    src = IngestSource(pack_source="community", applied_by=str(admin.user_id))
    any_error = False

    for yaml_body in yamls:
        # Each ingest runs in its own session so a failure in one
        # doesn't rollback the previous successes.
        try:
            async with sm() as ingest_session:
                result = await ingest_pack(
                    ingest_session,
                    sessionmaker=sm,
                    content=yaml_body.body,
                    source=src,
                )
                await ingest_session.commit()
            was_applied = result.action in ("applied", "reapplied")
            items.append(
                SyncItemOutcome(
                    filename=yaml_body.filename,
                    source_url=yaml_body.source_url,
                    outcome="applied" if was_applied else result.action,
                    pack_version=result.pack_version,
                )
            )
            if was_applied:
                applied_count += 1
        except (
            PackValidationError,
            PackVersionConflictError,
        ) as e:
            any_error = True
            items.append(
                SyncItemOutcome(
                    filename=yaml_body.filename,
                    source_url=yaml_body.source_url,
                    outcome="failed",
                    error=str(e)[:512],
                )
            )
        except Exception as e:  # noqa: BLE001
            any_error = True
            items.append(
                SyncItemOutcome(
                    filename=yaml_body.filename,
                    source_url=yaml_body.source_url,
                    outcome="failed",
                    error=f"{type(e).__name__}: {str(e)[:256]}",
                )
            )

    status_s = "error" if applied_count == 0 and any_error else (
        "partial" if any_error else "ok"
    )
    row.last_synced_at = fetched_at
    row.last_status = status_s
    row.last_error = (
        "; ".join(i.error for i in items if i.error)[:1024]
        if any_error
        else None
    )
    row.last_applied_count = applied_count
    await db.commit()

    return SyncResult(
        source_id=source_id,
        fetched_at=fetched_at,
        status=status_s,
        items=items,
        applied_count=applied_count,
    )


__all__ = ["router"]
