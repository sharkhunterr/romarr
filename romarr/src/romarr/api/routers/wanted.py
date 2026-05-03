"""Wanted lists — `/missing` and `/cutoff` (T056, FR-014).

Spec 013 ships an `/api/v3/wanted` surface backed by the
:class:`Release` table from spec 001 / 007. Two paginated reads:

  * **`/wanted/missing`** — releases the operator has marked
    monitored but Romarr hasn't yet acquired. Filter:
    ``status = 'wanted' AND monitored = true``.
  * **`/wanted/cutoff`** — releases that ARE imported but don't
    meet the configured upgrade cutoff. Filter:
    ``status = 'imported' AND cutoff_met = false AND monitored = true``.

The bulk-search trigger
(POST `/wanted/missing/search`) needs the spec 007
``run_manual_search`` hook and lands in a follow-up slice.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.api.envelopes import PaginationEnvelope
from romarr.api.pagination import PageRequest, page_request, paginate
from romarr.auth import Principal
from romarr.domain.models import Game, Release

router = APIRouter(prefix="/api/v3/wanted", tags=["Wanted"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class WantedReleaseRead(BaseModel):
    """Sonarr-shape camelCase JSON for a wanted release.

    Mirrors only the fields the Wanted page UI reads — the full
    Release detail is on the Game tabbed view, not here. Keeps
    payload small for typical 50-row pages."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    game_id: int = Field(alias="gameId")
    name: str
    regions: list[str]
    languages: list[str]
    revision: str | None = None
    dump_status: str = Field(alias="dumpStatus")
    naming_convention: str = Field(alias="namingConvention")
    status: str
    monitored: bool
    cutoff_met: bool = Field(alias="cutoffMet")
    library_id: int | None = Field(alias="libraryId", default=None)
    disc_number: int = Field(alias="discNumber")
    disc_total: int = Field(alias="discTotal")
    parent_release_id: int | None = Field(
        alias="parentReleaseId", default=None
    )
    created_at: Any = Field(alias="createdAt")
    updated_at: Any = Field(alias="updatedAt")


def _adapt(row: Release) -> WantedReleaseRead:
    return WantedReleaseRead.model_validate(row)


# Both endpoints share the sortable whitelist. ``id`` is first
# (default), then operator-friendly columns.
_SORTABLE_KEYS = {
    "id": Release.id,
    "name": Release.name,
    "created_at": Release.created_at,
    "updated_at": Release.updated_at,
    "status": Release.status,
}


# ---------------------------------------------------------------------------
# GET /api/v3/wanted/missing
# ---------------------------------------------------------------------------


@router.get(
    "/missing",
    response_model=PaginationEnvelope[WantedReleaseRead],
    response_model_by_alias=True,
    summary=(
        "Releases the operator has flagged monitored but Romarr "
        "hasn't acquired yet (status='wanted')."
    ),
)
async def list_missing(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page_req: Annotated[PageRequest, Depends(page_request)],
    platform_id: Annotated[
        int | None,
        Query(
            alias="platformId",
            ge=1,
            description="Restrict to one platform (joined via Game).",
        ),
    ] = None,
) -> PaginationEnvelope[WantedReleaseRead]:
    base = select(Release).where(
        Release.status == "wanted",
        Release.monitored.is_(True),
    )
    if platform_id is not None:
        base = base.join(Game, Release.game_id == Game.id).where(
            Game.platform_id == platform_id
        )
    return await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=_SORTABLE_KEYS,
        record_adapter=_adapt,
    )


# ---------------------------------------------------------------------------
# GET /api/v3/wanted/cutoff
# ---------------------------------------------------------------------------


@router.get(
    "/cutoff",
    response_model=PaginationEnvelope[WantedReleaseRead],
    response_model_by_alias=True,
    summary=(
        "Releases that ARE imported but don't yet meet the "
        "configured upgrade cutoff (cutoff_met=false)."
    ),
)
async def list_cutoff(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page_req: Annotated[PageRequest, Depends(page_request)],
    platform_id: Annotated[
        int | None,
        Query(
            alias="platformId",
            ge=1,
            description="Restrict to one platform (joined via Game).",
        ),
    ] = None,
) -> PaginationEnvelope[WantedReleaseRead]:
    base = select(Release).where(
        Release.status == "imported",
        Release.cutoff_met.is_(False),
        Release.monitored.is_(True),
    )
    if platform_id is not None:
        base = base.join(Game, Release.game_id == Game.id).where(
            Game.platform_id == platform_id
        )
    return await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=_SORTABLE_KEYS,
        record_adapter=_adapt,
    )


__all__ = ["router"]
