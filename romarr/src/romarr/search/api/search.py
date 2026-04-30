"""Manual search HTTP surface — POST /api/v3/rom/search/manual.

Admin-gated (FR-026). Non-strict by default; with ``?strict=true``
the response excludes auto-rejected candidates.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.search._clients import make_indexer_client_factory
from romarr.search.rounds.manual import run_manual_search
from romarr.search.schemas import ManualSearchRequest
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
