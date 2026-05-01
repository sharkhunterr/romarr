"""Import-history endpoint — `GET /api/v3/rom/import/history`.

Read-only paginated list of every import round, success or
failure. Per FR-038a accessible to any authenticated user (the
operator's library / activity views render against this).
Filterable by ``game_id``, ``release_id``, ``imported_via``, and
``success`` (the "show me failures" filter).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.importer.models import ImportHistory
from romarr.importer.schemas import ImportHistoryRead

router = APIRouter(prefix="/api/v3/rom/import", tags=["Importer"])


@router.get(
    "/history",
    response_model=list[ImportHistoryRead],
    summary=(
        "List import-history rows (any authenticated user). "
        "Paginated; filterable by game_id / release_id / imported_via / success."
    ),
)
async def list_history(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int | None, Query(ge=1)] = None,
    release_id: Annotated[int | None, Query(ge=1)] = None,
    imported_via: Annotated[
        Literal["automatic", "manual", "rss", "api", "webhook"] | None,
        Query(),
    ] = None,
    success: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ImportHistoryRead]:
    stmt = select(ImportHistory).order_by(ImportHistory.started_at.desc())
    if game_id is not None:
        stmt = stmt.where(ImportHistory.game_id == game_id)
    if release_id is not None:
        stmt = stmt.where(ImportHistory.release_id == release_id)
    if imported_via is not None:
        stmt = stmt.where(ImportHistory.imported_via == imported_via)
    if success is not None:
        stmt = stmt.where(ImportHistory.success == success)
    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).scalars().all()
    return [ImportHistoryRead.model_validate(r, from_attributes=True) for r in rows]


__all__ = ["router"]
