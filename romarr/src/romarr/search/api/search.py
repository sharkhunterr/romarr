"""Manual / release search HTTP surface.

Both endpoints are admin-gated (FR-026). The ``strict`` flag drops
candidates that would auto-reject from the response.

* ``POST /api/v3/rom/search/manual`` — free-form query against
  factory-default profiles.
* ``POST /api/v3/rom/search/release/{id}`` — query derived from the
  Release's parent Game, gates run against the Release's bound
  Library profiles (T062).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.search._clients import make_indexer_client_factory
from romarr.search.rounds.manual import run_manual_search
from romarr.search.rounds.release import run_release_search
from romarr.search.schemas import ManualSearchRequest, ReleaseSearchRequest
from romarr.search.types import SearchRoundReport

router = APIRouter(prefix="/api/v3/rom/search", tags=["Search"])


@router.post(
    "/manual",
    response_model=SearchRoundReport,
    status_code=status.HTTP_200_OK,
    summary="Run a manual search round (admin only).",
)
async def manual_search(
    body: Annotated[ManualSearchRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SearchRoundReport:
    factory = make_indexer_client_factory(db)
    return await run_manual_search(
        session=db,
        query=body.query,
        client_factory=factory,
        indexer_ids=body.indexer_ids,
        platform_id=body.platform_id,
        strict=body.strict,
    )


@router.post(
    "/release/{release_id}",
    response_model=SearchRoundReport,
    status_code=status.HTTP_200_OK,
    summary="Run a release-scoped search round (admin only).",
)
async def release_search(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    release_id: Annotated[int, Path(ge=1)],
    body: Annotated[ReleaseSearchRequest | None, Body()] = None,
) -> SearchRoundReport:
    payload = body or ReleaseSearchRequest()
    factory = make_indexer_client_factory(db)
    return await run_release_search(
        session=db,
        release_id=release_id,
        client_factory=factory,
        indexer_ids=payload.indexer_ids,
        strict=payload.strict,
    )
