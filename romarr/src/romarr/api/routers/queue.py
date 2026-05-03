"""Queue-mirror endpoints (T057, FR-014).

Spec 013 ships an ``/api/v3/queue`` surface backed by the
:class:`QueueEntry` table from spec 013 data-model. The Activity
page UI reads from this; the spec 005 reconciler writes / updates
rows on grab + every poll.

This slice ships the list (GET) endpoint with the canonical
pagination envelope. The mutating endpoints (DELETE with
``?removeFromClient=true``, POST ``/{id}/retry``) require the
spec 005 ``DownloadClient.remove`` / ``add_*`` integration and
land in a follow-up slice.

Sortable keys default to ``last_updated_at desc`` — operators
care about freshness; the Activity page polls / WS-subscribes
and expects newest movement first. ``state`` and ``progress``
are also sortable for the "what's stuck" / "what's almost done"
filtering flows.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.api.envelopes import PaginationEnvelope
from romarr.api.models import QueueEntry
from romarr.api.pagination import PageRequest, page_request, paginate
from romarr.auth import Principal
from romarr.domain.models import Release

router = APIRouter(prefix="/api/v3/queue", tags=["Queue"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class QueueEntryRead(BaseModel):
    """One queue entry — Sonarr-shape camelCase JSON."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    release_id: int = Field(alias="releaseId")
    download_client_id: int = Field(alias="downloadClientId")
    download_client_native_id: str = Field(alias="downloadClientNativeId")
    state: str
    progress: float
    size_bytes: int | None = Field(alias="sizeBytes", default=None)
    eta_seconds: int | None = Field(alias="etaSeconds", default=None)
    last_updated_at: Any = Field(alias="lastUpdatedAt")
    error_msg: str | None = Field(alias="errorMsg", default=None)
    attempt_count: int = Field(alias="attemptCount")
    last_attempt_at: Any = Field(alias="lastAttemptAt", default=None)
    created_at: Any = Field(alias="createdAt")


def _adapt(row: QueueEntry) -> QueueEntryRead:
    return QueueEntryRead.model_validate(row)


# Sortable column whitelist — endpoint declares its operator-facing
# names; the canonical paginate() raises 400 with errorCode
# ``invalid_sort_key`` for anything else.
_SORTABLE_KEYS = {
    "last_updated_at": QueueEntry.last_updated_at,
    "state": QueueEntry.state,
    "progress": QueueEntry.progress,
    "created_at": QueueEntry.created_at,
    "id": QueueEntry.id,
}


# ---------------------------------------------------------------------------
# GET /api/v3/queue
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginationEnvelope[QueueEntryRead],
    response_model_by_alias=True,
    summary=(
        "Paginated list of active download-client queue entries. "
        "Mirror of each download client's queue, refreshed by the "
        "spec 005 reconciler."
    ),
)
async def list_queue(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page_req: Annotated[PageRequest, Depends(page_request)],
    game_id: Annotated[
        int | None,
        Query(
            alias="gameId",
            ge=1,
            description=(
                "Filter to entries whose Release belongs to the given "
                "Game (joined via release_id → release.game_id)."
            ),
        ),
    ] = None,
    release_id: Annotated[
        int | None,
        Query(
            alias="releaseId",
            ge=1,
            description="Filter to a single Release.",
        ),
    ] = None,
) -> PaginationEnvelope[QueueEntryRead]:
    """Returns every queue_entry row matching the page request.

    Default sort is ``last_updated_at`` ascending; callers
    typically pass ``?sortKey=last_updated_at&sortDirection=desc``
    to surface the freshest movement first.

    The optional ``gameId`` / ``releaseId`` filters drive the
    GameDetail per-game queue indicator (slice 109)."""
    base = select(QueueEntry)
    if release_id is not None:
        base = base.where(QueueEntry.release_id == release_id)
    if game_id is not None:
        base = base.join(
            Release, Release.id == QueueEntry.release_id
        ).where(Release.game_id == game_id)
    return await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=_SORTABLE_KEYS,
        record_adapter=_adapt,
    )


__all__ = ["router"]
