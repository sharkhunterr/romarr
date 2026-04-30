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
from romarr.auth import Principal
from romarr.downloaders.models import DownloadClient
from romarr.downloaders.routing import RoutingCandidate
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

    started_at = datetime.now(UTC)
    outcome = await dispatch_winner(
        candidate=candidate,
        candidates=candidates_for_routing,
        client_factory=factory,
    )
    finished_at = datetime.now(UTC)

    correlation_id = str(uuid.uuid4())
    no_grab_reason = (
        None
        if outcome.status is DispatchStatus.GRABBED
        else outcome.status.value
    )
    await record_round(
        db,
        correlation_id=correlation_id,
        search_type="manual",
        query=None,
        indexer_results=[
            {
                "indexer_id": body.indexer_id,
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
