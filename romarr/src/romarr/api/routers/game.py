"""Game + Release read endpoints (slice 86).

Foundation already ships the :class:`Game` + :class:`Release`
ORM models; this router is the operator-facing read surface
the frontend needs to back the manual-match Game picker
(slice 84's `POST /api/v3/rom/unidentified/{id}/match`
endpoint requires `game_id` + `release_id`).

Surface today:

  * `GET /api/v3/game` — list games with optional
    title-substring + platform-id filter, paginated.
  * `GET /api/v3/game/{game_id}` — single game read.
  * `GET /api/v3/game/{game_id}/release` — list every
    Release belonging to the game (the Frontend Match form
    needs this to populate the "which release" picker).

Write endpoints (POST / PUT / DELETE) intentionally omitted —
spec 002's metadata aggregator owns Game creation; the
operator-facing surface is "search IGDB + add" via
``/api/v3/game/lookup`` which lands with spec 010 once the
metadata-driven add flow is wired.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Game, Release
from romarr.domain.schemas import GameRead, ReleaseRead

router = APIRouter(prefix="/api/v3/game", tags=["Game"])


@router.get(
    "",
    response_model=list[GameRead],
    summary="List games (any authenticated user). Supports title-substring + platform filters.",
)
async def list_games(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str | None,
        Query(
            description=(
                "Case-insensitive substring filter on the game title. "
                "Trimmed; empty/whitespace-only ignored."
            ),
            max_length=255,
        ),
    ] = None,
    platform_id: Annotated[
        int | None, Query(ge=1, description="Restrict to one platform.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GameRead]:
    stmt = select(Game).order_by(Game.title.asc())
    if platform_id is not None:
        stmt = stmt.where(Game.platform_id == platform_id)
    if q is not None and q.strip():
        # Case-insensitive substring match. SQLite + Postgres
        # both honor `lower(title) LIKE lower('%term%')` so this
        # is portable across the two database backends spec 001
        # supports.
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(Game.title).like(needle))
    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        GameRead.model_validate(row, from_attributes=True) for row in rows
    ]


@router.get(
    "/{game_id}",
    response_model=GameRead,
    summary="Read one game (any authenticated user).",
)
async def read_game(
    game_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameRead:
    row = (
        await db.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={game_id} not found",
                "errorCode": "game_not_found",
            },
        )
    return GameRead.model_validate(row, from_attributes=True)


@router.get(
    "/{game_id}/release",
    response_model=list[ReleaseRead],
    summary=(
        "List every Release for a game. Drives the Match form's "
        "Release picker."
    ),
)
async def list_releases_for_game(
    game_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ReleaseRead]:
    # Verify the game exists so a typo'd id surfaces as 404
    # rather than an empty list (which would mislead the
    # operator into thinking the game has zero releases).
    game = (
        await db.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={game_id} not found",
                "errorCode": "game_not_found",
            },
        )

    rows = (
        await db.execute(
            select(Release)
            .where(Release.game_id == game_id)
            .order_by(Release.disc_number.asc(), Release.name.asc())
        )
    ).scalars().all()
    return [
        ReleaseRead.model_validate(row, from_attributes=True) for row in rows
    ]


__all__ = ["router"]
