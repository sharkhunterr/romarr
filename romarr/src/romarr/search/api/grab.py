"""Manual grab endpoint — POST /api/v3/rom/release/grab.

Operator picks a specific indexer result + downloader pair from a
manual-search response. The blocklist gate fires unless
``?force=true`` is supplied (FR-022 / SC-006).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.api.models import QueueEntry
from romarr.auth import Principal
from romarr.downloaders.models import DownloadClient
from romarr.downloaders.routing import RoutingCandidate
from romarr.downloaders.types import SourceKind
from romarr.indexers.models import Indexer
from romarr.indexers.types import SearchResult
from romarr.search._clients import make_download_client_factory
from romarr.search.blocklist import is_blocklisted
from romarr.search.dispatch import DispatchStatus, dispatch_winner
from romarr.search.history import record_round
from romarr.search.schemas import GrabRequest
from romarr.search.types import Candidate

router = APIRouter(prefix="/api/v3/rom/release", tags=["Search"])


def _result_from_request(req: GrabRequest) -> SearchResult:
    return SearchResult(
        indexer_id=req.indexer_id,
        guid=req.indexer_guid,
        title=req.title,
        link=req.download_url,
    )


def _candidate_from_request(req: GrabRequest) -> Candidate:
    return Candidate(
        indexer_id=req.indexer_id,
        indexer_guid=req.indexer_guid,
        title=req.title,
        download_url=req.download_url,
        matched_release_id=req.release_id,
        score_breakdown=None,
        rejection=None,
        would_auto_reject=False,
    )


async def _routing_candidates(session: AsyncSession) -> list[RoutingCandidate]:
    rows = (await session.execute(select(DownloadClient))).scalars().all()
    return [
        RoutingCandidate(
            id=row.id,
            priority=row.priority,
            enabled=row.enabled,
            enable_for_torrents=row.enable_for_torrents,
            enable_for_usenet=row.enable_for_usenet,
        )
        for row in rows
    ]


@router.post(
    "/grab",
    status_code=status.HTTP_200_OK,
    summary=(
        "Manual grab of one indexer result (admin only). "
        "``?force=true`` overrides the blocklist gate."
    ),
)
async def manual_grab(
    body: Annotated[GrabRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: Annotated[bool, Query(description="Override the blocklist gate")] = False,
) -> dict[str, Any]:
    result = _result_from_request(body)

    if not force:
        existing = await is_blocklisted(db, result=result)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "errorMessage": "release_blocklisted",
                    "errorCode": "blocklisted",
                    "details": existing.reason,
                },
            )

    candidate = _candidate_from_request(body)
    candidates_for_routing = await _routing_candidates(db)
    factory = make_download_client_factory(db)

    # Derive the source kind from the originating indexer's
    # ``implementation``. Prowlarr's download URL is opaque
    # (``/<id>/download?apikey=…&link=…``) so the URL sniffer
    # in ``dispatch_winner`` can't tell torrent from nzb — we
    # used to default everything to USENET, which broke routing
    # the moment an operator only had a qBittorrent configured.
    indexer_row = (
        await db.execute(select(Indexer).where(Indexer.id == body.indexer_id))
    ).scalar_one_or_none()
    source_kind = (
        SourceKind.TORRENT
        if indexer_row is not None and indexer_row.implementation == "torznab"
        else SourceKind.USENET
        if indexer_row is not None and indexer_row.implementation == "newznab"
        else None  # falls back to URL sniffing
    )

    started_at = datetime.now(UTC)
    outcome = await dispatch_winner(
        candidate=candidate,
        candidates=candidates_for_routing,
        client_factory=factory,
        source_kind=source_kind,
    )
    finished_at = datetime.now(UTC)

    correlation_id = str(uuid.uuid4())
    no_grab_reason = (
        None
        if outcome.status is DispatchStatus.GRABBED
        else outcome.status.value
    )

    # Mirror the just-accepted grab into the ``queue_entry``
    # table so the Activity → Queue page picks it up
    # immediately. The reconciler / poll loop owns subsequent
    # progress updates; we only insert the initial row in the
    # ``downloading`` state. Skipped when there's no release id
    # (game-level manual search) — the queue_entry FK is
    # NOT NULL on release_id and a row without a release would
    # have nothing to reconcile back to.
    if (
        outcome.status is DispatchStatus.GRABBED
        and outcome.client_id is not None
        and outcome.client_native_id is not None
        and body.release_id is not None
    ):
        # Upsert by (download_client_id, native_id) so reruns of
        # the same grab don't 409 on the unique constraint.
        existing = (
            await db.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_id == outcome.client_id,
                    QueueEntry.download_client_native_id
                    == outcome.client_native_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                QueueEntry(
                    release_id=body.release_id,
                    download_client_id=outcome.client_id,
                    download_client_native_id=outcome.client_native_id,
                    state="downloading",
                    progress=0.0,
                )
            )
            await db.commit()
    await record_round(
        db,
        correlation_id=correlation_id,
        search_type="manual",
        query=None,
        indexer_results=[
            {
                "indexer_id": body.indexer_id,
                "game_id": body.game_id,
                "release_id": body.release_id,
                "results_count": 1,
                "grabbed_release_id": (
                    body.release_id
                    if outcome.status is DispatchStatus.GRABBED
                    else None
                ),
                "chosen_indexer_guid": body.indexer_guid,
                "no_grab_reason": no_grab_reason,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": int(
                    (finished_at - started_at).total_seconds() * 1000
                ),
            }
        ],
    )

    return {
        "status": outcome.status.value,
        "client_id": outcome.client_id,
        "client_native_id": outcome.client_native_id,
        "reason": outcome.reason,
        "correlation_id": correlation_id,
    }
