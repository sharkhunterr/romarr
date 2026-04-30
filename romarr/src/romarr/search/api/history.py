"""Search history read endpoint — GET /api/v3/rom/search/history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.search.models import SearchHistory
from romarr.search.schemas import SearchHistoryRead
from romarr.search.types import SearchType

router = APIRouter(prefix="/api/v3/rom/search", tags=["Search"])


@router.get(
    "/history",
    response_model=list[SearchHistoryRead],
    summary="List search-history rows (admin only). Filterable by game / type.",
)
async def list_history(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int | None, Query(description="Filter by Game id")] = None,
    search_type: Annotated[
        SearchType | None,
        Query(description="Filter by search mode"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SearchHistoryRead]:
    stmt = select(SearchHistory).order_by(SearchHistory.started_at.desc())
    if game_id is not None:
        stmt = stmt.where(SearchHistory.game_id == game_id)
    if search_type is not None:
        stmt = stmt.where(SearchHistory.search_type == search_type)
    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [SearchHistoryRead.model_validate(r, from_attributes=True) for r in rows]
