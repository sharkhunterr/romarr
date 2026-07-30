"""Unified Update Center endpoints — ``/api/v3/community/*``.

  - GET    /api/v3/community/source                — list (all resource_types)
  - POST   /api/v3/community/source                — create + first check
  - PATCH  /api/v3/community/source/{id}           — enable / auto_check / trust
  - DELETE /api/v3/community/source/{id}           — remove
  - POST   /api/v3/community/source/{id}/check     — force refresh
  - POST   /api/v3/community/source/{id}/apply     — fetch bodies + ingest
  - GET    /api/v3/community/updates               — aggregated update badge feed
                                                     (community sources + Romarr GitHub)

Admin-only for mutations. GET endpoints require any authenticated
user (they surface no PII).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import romarr.community  # noqa: F401 — registers adapters
from romarr import __version__
from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.api.version_check import check_latest_release
from romarr.auth import Principal
from romarr.community.sync import apply_source, check_source
from romarr.community.versioning import is_newer
from romarr.platform_packs.models import PackSource

router = APIRouter(prefix="/api/v3/community", tags=["Community"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class SourceRead(_Base):
    id: int
    name: str
    url: str
    kind: str
    resource_type: str
    enabled: bool
    auto_check: bool
    trust_status: str

    last_synced_at: datetime | None
    last_status: str | None
    last_error: str | None
    last_applied_count: int
    last_seen_version: str | None
    installed_version: str | None

    update_available: bool

    @classmethod
    def from_row(cls, row: PackSource) -> "SourceRead":
        return cls(
            id=row.id,
            name=row.name,
            url=row.url,
            kind=row.kind,
            resource_type=row.resource_type,
            enabled=row.enabled,
            auto_check=row.auto_check,
            trust_status=row.trust_status,
            last_synced_at=row.last_synced_at,
            last_status=row.last_status,
            last_error=row.last_error,
            last_applied_count=row.last_applied_count,
            last_seen_version=row.last_seen_version,
            installed_version=row.installed_version,
            update_available=is_newer(
                row.last_seen_version, row.installed_version
            ),
        )


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=128)
    url: HttpUrl
    resource_type: Literal["platform_pack", "custom_format"]
    kind: Literal["raw", "github_dir"] = "raw"


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool | None = None
    auto_check: bool | None = None
    trust_status: Literal["pending", "trusted"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)


class CheckResponse(BaseModel):
    source: SourceRead
    available_version: str | None
    manifest_name: str | None
    item_count: int
    error: str | None


class ApplyResponse(BaseModel):
    source: SourceRead
    applied_version: str
    applied_count: int
    warnings: list[str]
    error: str | None


class RomarrUpdate(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    release_url: str | None
    error: str | None


class UpdatesFeed(BaseModel):
    romarr: RomarrUpdate
    sources: list[SourceRead]
    total_updates: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/source", response_model=list[SourceRead])
async def list_sources(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    resource_type: (
        Literal["platform_pack", "custom_format"] | None
    ) = None,
) -> list[SourceRead]:
    """List every registered community source, optionally filtered
    by ``resource_type`` (query param). Order: oldest-first for
    stable UI order."""
    stmt = select(PackSource).order_by(PackSource.id.asc())
    if resource_type is not None:
        stmt = stmt.where(PackSource.resource_type == resource_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [SourceRead.from_row(r) for r in rows]


@router.post(
    "/source",
    response_model=CheckResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    payload: SourceCreate,
    _principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckResponse:
    """Register a new source. Auto-runs the first ``check`` so the
    UI can preview the manifest immediately. Trust status starts
    ``pending`` — the operator must click "Trust + Apply" once
    before auto-apply can happen."""
    existing = (
        await db.execute(
            select(PackSource).where(PackSource.name == payload.name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a source named {payload.name!r} already exists",
        )

    row = PackSource(
        name=payload.name,
        url=str(payload.url),
        kind=payload.kind,
        resource_type=payload.resource_type,
        enabled=True,
        auto_check=True,
        trust_status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    result = await check_source(row, db)
    return CheckResponse(
        source=SourceRead.from_row(row),
        available_version=result.available_version,
        manifest_name=result.manifest_name,
        item_count=result.item_count,
        error=result.error,
    )


async def _get_source(db: AsyncSession, source_id: int) -> PackSource:
    row = await db.get(PackSource, source_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"source id={source_id} not found",
        )
    return row


@router.patch("/source/{source_id}", response_model=SourceRead)
async def patch_source(
    source_id: int,
    payload: SourcePatch,
    _principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceRead:
    row = await _get_source(db, source_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return SourceRead.from_row(row)


@router.delete("/source/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: int,
    _principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = await _get_source(db, source_id)
    await db.delete(row)
    await db.commit()


@router.post("/source/{source_id}/check", response_model=CheckResponse)
async def check_source_now(
    source_id: int,
    _principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckResponse:
    row = await _get_source(db, source_id)
    result = await check_source(row, db)
    return CheckResponse(
        source=SourceRead.from_row(row),
        available_version=result.available_version,
        manifest_name=result.manifest_name,
        item_count=result.item_count,
        error=result.error,
    )


@router.post("/source/{source_id}/apply", response_model=ApplyResponse)
async def apply_source_now(
    source_id: int,
    _principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplyResponse:
    row = await _get_source(db, source_id)
    result = await apply_source(row, db)
    return ApplyResponse(
        source=SourceRead.from_row(row),
        applied_version=result.applied_version,
        applied_count=result.applied_count,
        warnings=list(result.warnings),
        error=result.error,
    )


_GITHUB_REPO = "sharkhunterr/romarr"


@router.get("/updates", response_model=UpdatesFeed)
async def updates_feed(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UpdatesFeed:
    """Aggregate feed the UpdateCenterBadge reads.

    Combines the Romarr GitHub release check (cached 1h in-process
    by :mod:`romarr.api.version_check`) with every registered
    community source. Returns the full source list so the popover
    can render both "up to date" and "N updates available" sections."""
    romarr_info = await check_latest_release(
        current_version=__version__, github_repo=_GITHUB_REPO
    )
    romarr = RomarrUpdate(
        current=romarr_info.current,
        latest=romarr_info.latest,
        update_available=romarr_info.update_available,
        release_url=romarr_info.release_url,
        error=romarr_info.error,
    )

    rows = (
        (await db.execute(select(PackSource).order_by(PackSource.id.asc())))
        .scalars()
        .all()
    )
    sources = [SourceRead.from_row(r) for r in rows]
    community_updates = sum(1 for s in sources if s.update_available)
    total = community_updates + (1 if romarr.update_available else 0)

    return UpdatesFeed(
        romarr=romarr, sources=sources, total_updates=total
    )
