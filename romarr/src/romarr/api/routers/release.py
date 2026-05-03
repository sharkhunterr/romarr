"""Release write endpoints (slices 98, 152, 155).

The spec 014 GameDetail > Releases tab calls for per-release
operator actions: monitor toggle, manual search, manual grab,
delete. Manual grab already exists at
``POST /api/v3/rom/release/grab`` (spec 007). This router
ships the operator-toggle / bulk surface:

  * ``PATCH /api/v3/rom/release/{release_id}`` — toggle the
    Release's ``monitored`` flag (admin only).
  * ``POST  /api/v3/rom/release/bulk-monitor`` — flip the flag
    on a batch of releases (admin only).
  * ``POST  /api/v3/rom/release/bulk-delete`` — delete a batch
    of releases (admin only). Per the constitution this never
    touches files on disk — only the database row + cascaded
    Dump rows go away. Per-library lifecycle policies own the
    on-disk side.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.domain.models import Release
from romarr.domain.schemas import ReleaseRead


class ReleaseToggleRequest(BaseModel):
    """PATCH /api/v3/rom/release/{id} — operator-toggle subset.

    ``extra=forbid`` keeps this surface narrow: free-form
    Release edits (region, naming, dump_status, etc.) belong
    to the import pipeline / DAT identification flows, not
    to a hand-rolled PATCH.
    """

    model_config = ConfigDict(extra="forbid")

    monitored: bool


class BulkReleaseMonitorRequest(BaseModel):
    """POST /api/v3/rom/release/bulk-monitor — slice 152.

    Mirrors the slice-151 Game bulk-monitor surface but on
    Releases. Capped at 500 ids per call; the UI shards larger
    selections client-side.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    release_ids: Annotated[
        list[int],
        Field(alias="releaseIds", min_length=1, max_length=500),
    ]
    monitored: bool


class BulkReleaseMonitorResponse(BaseModel):
    """Response envelope for the release bulk-monitor endpoint."""

    model_config = ConfigDict(extra="forbid")

    updated: int
    missing: list[int]


class BulkReleaseDeleteRequest(BaseModel):
    """POST /api/v3/rom/release/bulk-delete — slice 155.

    Same shape contract as the Game bulk-delete endpoint but
    on Release ids. Cascades to the Release's Dump rows; never
    touches files on disk.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    release_ids: Annotated[
        list[int],
        Field(alias="releaseIds", min_length=1, max_length=500),
    ]


class BulkReleaseDeleteResponse(BaseModel):
    """Response envelope for the release bulk-delete endpoint."""

    model_config = ConfigDict(extra="forbid")

    deleted: int
    missing: list[int]


router = APIRouter(prefix="/api/v3/rom/release", tags=["Release"])


@router.post(
    "/bulk-monitor",
    response_model=BulkReleaseMonitorResponse,
    summary=(
        "Flip the monitored flag on a batch of Releases (admin "
        "only). Capped at 500 ids per call. Returns the number "
        "of rows updated and the ids that didn't resolve."
    ),
)
async def bulk_monitor_releases(
    body: Annotated[BulkReleaseMonitorRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkReleaseMonitorResponse:
    rows = (
        (
            await db.execute(
                select(Release).where(Release.id.in_(body.release_ids))
            )
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = sorted(set(body.release_ids) - found)
    for row in rows:
        row.monitored = body.monitored
    await db.commit()
    return BulkReleaseMonitorResponse(updated=len(rows), missing=missing)


@router.post(
    "/bulk-delete",
    response_model=BulkReleaseDeleteResponse,
    summary=(
        "Delete a batch of Releases — and their Dumps via "
        "cascade — without touching ROM files on disk (admin "
        "only). Capped at 500 ids per call."
    ),
)
async def bulk_delete_releases(
    body: Annotated[BulkReleaseDeleteRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkReleaseDeleteResponse:
    rows = (
        (
            await db.execute(
                select(Release).where(Release.id.in_(body.release_ids))
            )
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = sorted(set(body.release_ids) - found)
    for row in rows:
        await db.delete(row)
    await db.commit()
    return BulkReleaseDeleteResponse(deleted=len(rows), missing=missing)


@router.patch(
    "/{release_id}",
    response_model=ReleaseRead,
    summary=(
        "Toggle a Release's ``monitored`` flag (admin only). "
        "All other fields are owned by the import pipeline."
    ),
)
async def patch_release(
    release_id: int,
    body: Annotated[ReleaseToggleRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReleaseRead:
    row = (
        await db.execute(select(Release).where(Release.id == release_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"release_id={release_id} not found",
                "errorCode": "release_not_found",
            },
        )
    row.monitored = body.monitored
    await db.commit()
    await db.refresh(row)
    return ReleaseRead.model_validate(row, from_attributes=True)


__all__ = ["router"]
