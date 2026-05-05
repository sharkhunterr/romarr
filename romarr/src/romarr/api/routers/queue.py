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

from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.api.envelopes import PaginationEnvelope
from romarr.api.models import QueueEntry
from romarr.api.pagination import PageRequest, page_request, paginate
from romarr.auth import Principal
from romarr.domain.models import Release


# Sync with the CHECK constraint in api/models.py — Literal-typed
# query param so FastAPI rejects unknown states with 422 at the
# router edge instead of letting them through to the WHERE clause.
QueueState = Literal[
    "queued",
    "downloading",
    "paused",
    "completed",
    "stuck",
    "failed",
    "pending_retry",
]

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
    state: Annotated[
        QueueState | None,
        Query(
            description=(
                "Filter to one of the documented queue states "
                "(queued / downloading / paused / completed / "
                "stuck / failed / pending_retry). Drives the "
                "Activity > Queue state-filter chips."
            ),
        ),
    ] = None,
) -> PaginationEnvelope[QueueEntryRead]:
    """Returns every queue_entry row matching the page request.

    Default sort is ``last_updated_at`` ascending; callers
    typically pass ``?sortKey=last_updated_at&sortDirection=desc``
    to surface the freshest movement first.

    The optional ``gameId`` / ``releaseId`` filters drive the
    GameDetail per-game queue indicator (slice 109). The
    ``state`` filter (slice 121) drives the Activity > Queue
    state chips."""
    base = select(QueueEntry)
    if release_id is not None:
        base = base.where(QueueEntry.release_id == release_id)
    if game_id is not None:
        base = base.join(
            Release, Release.id == QueueEntry.release_id
        ).where(Release.game_id == game_id)
    if state is not None:
        base = base.where(QueueEntry.state == state)
    return await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=_SORTABLE_KEYS,
        record_adapter=_adapt,
    )


# ---------------------------------------------------------------------------
# DELETE /api/v3/queue/{id} — remove the entry, optionally tell the client to drop it
# ---------------------------------------------------------------------------


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Remove a queue entry (admin only). "
        "``?removeFromClient=true`` also asks the originating "
        "download client to drop the underlying download + its "
        "files; default false leaves the client untouched and "
        "only deletes the Romarr-side row."
    ),
    responses={
        204: {"description": "Removed."},
        404: {"description": "No queue entry with this id."},
        502: {
            "description": (
                "Download client refused the remove request "
                "(connection / auth / version error). The Romarr "
                "row is preserved so a retry is meaningful."
            )
        },
    },
)
async def delete_queue_entry(
    entry_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    remove_from_client: Annotated[
        bool,
        Query(
            alias="removeFromClient",
            description=(
                "When true, also call ``DownloadClient.remove`` on "
                "the originating client so the download + its on-"
                "disk files are dropped. Default false: only the "
                "Romarr-side mirror is cleared."
            ),
        ),
    ] = False,
) -> Response:
    entry = (
        await db.execute(
            select(QueueEntry).where(QueueEntry.id == entry_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "queue_entry_not_found",
                "errorCode": "queue_entry_not_found",
            },
        )

    if remove_from_client:
        # Build the spec 005 DownloadClient via the same factory
        # the manual-grab endpoint uses so the auth / TLS /
        # category-ensure plumbing is shared.
        from romarr.downloaders.errors import (
            AuthError,
            VersionError,
        )
        from romarr.downloaders.errors import (
            ConnectionError as DownloaderConnError,
        )
        from romarr.search._clients import make_download_client_factory

        factory = make_download_client_factory(db)
        try:
            client = await factory(entry.download_client_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "errorMessage": "download_client_unreachable",
                    "errorCode": "download_client_unreachable",
                    "details": f"client construction failed: {exc}",
                },
            ) from exc

        try:
            await client.remove(
                entry.download_client_native_id,
                delete_files=True,
            )
        except (DownloaderConnError, AuthError, VersionError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "errorMessage": "download_client_remove_failed",
                    "errorCode": "download_client_remove_failed",
                    "details": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "errorMessage": "download_client_remove_failed",
                    "errorCode": "download_client_remove_failed",
                    "details": f"unexpected: {exc}",
                },
            ) from exc

    await db.delete(entry)
    await db.commit()

    # Slice 275 — fan out a ``queueUpdated`` WS event so live
    # Activity tabs invalidate their queue query immediately. The
    # bridge is best-effort: a missing bridge (test harness) is
    # a silent no-op.
    bridge = getattr(request.app.state, "ws_bridge", None)
    if bridge is not None:
        from romarr.api.ws.messages import MessageType

        await bridge.emit_message(
            MessageType.QUEUE_UPDATED,
            data={"entry_id": entry_id, "kind": "deleted"},
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{entry_id}/retry",
    response_model=QueueEntryRead,
    status_code=status.HTTP_200_OK,
    summary="Reset a STUCK or FAILED queue entry so the next "
    "scheduler tick re-fires it (admin only).",
    responses={
        404: {"description": "No queue entry with this id."},
        409: {
            "description": (
                "Entry is in a terminal-success state (``completed``)"
                " and can't be retried. Issue a fresh grab instead."
            )
        },
    },
)
async def retry_queue_entry(
    entry_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> QueueEntryRead:
    """T046 — manual queue-entry retry.

    Resets the entry's retry-cooldown bookkeeping
    (``last_attempt_at`` cleared, ``attempt_count`` reset) and
    transitions ``failed`` → ``stuck`` so the spec 012 scheduler
    tick picks it back up at the next cadence.

    The actual client re-fire (``add_torrent`` / ``add_nzb`` against
    the original download URL) lands with the spec 012 retry
    runner — today's endpoint is the state-only reset that
    re-arms the entry. Refuses ``completed`` entries with 409
    (a re-grab is the right path).
    """
    entry = (
        await db.execute(
            select(QueueEntry).where(QueueEntry.id == entry_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "queue_entry_not_found",
                "errorCode": "queue_entry_not_found",
            },
        )

    if entry.state == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "queue_entry_completed",
                "errorCode": "queue_entry_completed",
            },
        )

    entry.state = "stuck"
    entry.attempt_count = 0
    entry.last_attempt_at = None
    entry.error_msg = None
    await db.commit()
    await db.refresh(entry)

    bridge = getattr(request.app.state, "ws_bridge", None)
    if bridge is not None:
        from romarr.api.ws.messages import MessageType

        await bridge.emit_message(
            MessageType.QUEUE_UPDATED,
            data={"entry_id": entry_id, "kind": "retry-reset"},
        )

    return QueueEntryRead.model_validate(entry)


__all__ = ["router"]
