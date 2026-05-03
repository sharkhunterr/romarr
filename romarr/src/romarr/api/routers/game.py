"""Game + Release read + lock endpoints (slices 86, 146).

Foundation already ships the :class:`Game` + :class:`Release`
ORM models; this router is the operator-facing read surface
the frontend needs to back the manual-match Game picker
(slice 84's `POST /api/v3/rom/unidentified/{id}/match`
endpoint requires `game_id` + `release_id`).

Surface today:

  * `GET   /api/v3/game` — list games with optional
    title-substring + platform-id filter, paginated.
  * `GET   /api/v3/game/{game_id}` — single game read.
  * `GET   /api/v3/game/{game_id}/release` — list every
    Release belonging to the game (the Frontend Match form
    needs this to populate the "which release" picker).
  * `GET   /api/v3/game/{game_id}/dump` — list every Dump
    that belongs to a game (joined through Releases).
  * `PATCH /api/v3/game/{game_id}` — toggle ``monitored``
    (admin only). Other Game fields are owned by spec 002's
    metadata aggregator and stay immutable here.

Game creation + free-form metadata edits are out of scope —
spec 002 owns those; the operator-facing add flow is "search
IGDB + add" via ``/api/v3/game/lookup`` which lands with
spec 010.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Dump, Game, Release
from romarr.domain.schemas import DumpRead, GameRead, ReleaseRead
from romarr.metadata.types import ProviderField

# Whitelist of sortable Game columns. Operator-facing names map
# to ORM columns; anything else 422s at the FastAPI validator.
_SORT_KEYS = {
    "title": Game.title,
    "added_at": Game.created_at,
    "release_date": Game.release_date,
    "rating": Game.rating,
}
GameSortKey = Literal["title", "added_at", "release_date", "rating"]
SortDirection = Literal["asc", "desc"]


class GameToggleRequest(BaseModel):
    """PATCH /api/v3/game/{id} — operator-toggle subset.

    Only fields that are NOT owned by the metadata aggregator
    are mutable here. Today: just ``monitored``. Adding more
    operator-toggleable bits is straightforward — they go in
    this schema.
    """

    model_config = ConfigDict(extra="forbid")

    monitored: bool


class FieldLockRequest(BaseModel):
    """PATCH /api/v3/game/{id}/locked-fields — toggle one field.

    The slice-146 anti-RomM-#1770 surface. ``field`` is
    constrained to :class:`ProviderField` so the only fields
    the operator can lock are the ones the aggregator could
    overwrite — locking an unrecognised field would be a no-op
    that silently drifts.
    """

    model_config = ConfigDict(extra="forbid")

    field: ProviderField
    locked: bool


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
    monitored: Annotated[
        bool | None,
        Query(
            description=(
                "Filter on the `monitored` flag. `true` is the most "
                "common operator workflow (\"show me what I'm tracking\")."
            ),
        ),
    ] = None,
    sort: Annotated[
        GameSortKey,
        Query(
            description=(
                "Sort key — `title` (default), `added_at` (Game.created_at), "
                "`release_date`, or `rating`."
            ),
        ),
    ] = "title",
    direction: Annotated[
        SortDirection,
        Query(description="Sort direction (asc default)."),
    ] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GameRead]:
    column = _SORT_KEYS[sort]
    order = asc(column) if direction == "asc" else desc(column)
    # NULLs last on `release_date` / `rating` so the operator
    # gets meaningful rows first. SQLite + Postgres both honor
    # the `IS NULL` ASC / DESC pattern via SQLAlchemy.
    stmt = select(Game).order_by(column.is_(None).asc(), order, Game.id.asc())
    if platform_id is not None:
        stmt = stmt.where(Game.platform_id == platform_id)
    if monitored is not None:
        stmt = stmt.where(Game.monitored.is_(monitored))
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


@router.patch(
    "/{game_id}",
    response_model=GameRead,
    summary=(
        "Toggle a Game's ``monitored`` flag (admin only). "
        "All other fields are owned by the metadata aggregator."
    ),
)
async def patch_game(
    game_id: int,
    body: Annotated[GameToggleRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
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
    row.monitored = body.monitored
    await db.commit()
    await db.refresh(row)
    return GameRead.model_validate(row, from_attributes=True)


@router.patch(
    "/{game_id}/locked-fields",
    response_model=GameRead,
    summary=(
        "Lock or unlock one metadata field on a Game (admin "
        "only). Locked fields are skipped by the aggregator on "
        "every refresh — the constitutional anti-RomM-#1770 "
        "mechanism (FR-008)."
    ),
)
async def patch_locked_fields(
    game_id: int,
    body: Annotated[FieldLockRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
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

    # `locked_fields` is a JSON column — copy-mutate-reassign so
    # SQLAlchemy actually flushes the change. The membership set
    # is canonicalised by alphabetical sort so the JSON shape
    # stays stable across toggles.
    field_value = body.field.value
    current = set(row.locked_fields or [])
    if body.locked:
        current.add(field_value)
    else:
        current.discard(field_value)
    row.locked_fields = sorted(current)

    await db.commit()
    await db.refresh(row)
    return GameRead.model_validate(row, from_attributes=True)


@router.get(
    "/{game_id}/dump",
    response_model=list[DumpRead],
    summary=(
        "List every Dump that belongs to a game (joined through "
        "the game's Releases). Drives GameDetail > Files."
    ),
)
async def list_dumps_for_game(
    game_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DumpRead]:
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
            select(Dump)
            .join(Release, Dump.release_id == Release.id)
            .where(Release.game_id == game_id)
            .order_by(Release.disc_number.asc(), Dump.imported_at.desc())
        )
    ).scalars().all()
    return [
        DumpRead.model_validate(row, from_attributes=True) for row in rows
    ]


__all__ = ["router"]
