"""Release write endpoints (slice 98).

The spec 014 GameDetail > Releases tab calls for per-release
operator actions: monitor toggle, manual search, manual grab,
delete. Manual grab already exists at
``POST /api/v3/rom/release/grab`` (spec 007). This router
adds the operator-toggle surface:

  * ``PATCH /api/v3/rom/release/{release_id}`` — toggle the
    Release's ``monitored`` flag (admin only).

Delete is intentionally deferred; cascading a Release delete
through its Dumps + history rows is destructive and needs a
double-confirm + force-detach pattern matching the Library
delete (spec 009).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
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


router = APIRouter(prefix="/api/v3/rom/release", tags=["Release"])


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
