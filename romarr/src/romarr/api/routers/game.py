"""Game + Release read + lock + per-field edit + notes endpoints
(slices 86, 146, 147, 149).

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


# Mapping of editable text fields → (Game ORM attribute,
# DB max length). Slice 147 only ships text-shaped edits;
# numeric and list fields can join later via dedicated payloads
# without disturbing this surface.
_EDITABLE_TEXT_FIELDS: dict[ProviderField, tuple[str, int | None]] = {
    ProviderField.TITLE: ("title", 255),
    ProviderField.SUMMARY: ("summary", None),
    ProviderField.DEVELOPER: ("developer", 128),
    ProviderField.PUBLISHER: ("publisher", 128),
    ProviderField.AGE_RATING: ("age_rating", 16),
}


class NotesUpdateRequest(BaseModel):
    """PUT /api/v3/game/{id}/notes — operator-owned free text.

    The notes column is operator-owned and never touched by the
    metadata aggregator, so the surface is intentionally
    minimal: write the new value, get the updated Game back.
    Set ``notes=null`` (or empty string) to clear.
    """

    model_config = ConfigDict(extra="forbid")

    notes: str | None


class FieldEditRequest(BaseModel):
    """PATCH /api/v3/game/{id}/field — manual operator edit.

    The slice-147 edit-in-place half of the anti-RomM-#1770
    surface. Only text fields (title, summary, developer,
    publisher, age_rating) are editable here — numeric / list
    fields will join via their own dedicated payloads.

    ``value`` may be ``null`` to clear the field. ``auto_lock``
    defaults to True because operator edits are sticky by
    definition: an edit the aggregator silently overwrote next
    refresh is exactly the bug the constitution forbids.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field: ProviderField
    value: str | None = None
    auto_lock: bool = True


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


@router.patch(
    "/{game_id}/field",
    response_model=GameRead,
    summary=(
        "Manually edit one text metadata field on a Game (admin "
        "only). Title, summary, developer, publisher, age_rating "
        "are supported today; auto-locks the field by default so "
        "the aggregator stops overwriting it."
    ),
)
async def patch_field(
    game_id: int,
    body: Annotated[FieldEditRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameRead:
    spec = _EDITABLE_TEXT_FIELDS.get(body.field)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"field={body.field.value!r} is not a text-editable "
                    "field — only title, summary, developer, "
                    "publisher, age_rating are accepted here."
                ),
                "errorCode": "field_not_editable",
            },
        )
    column_name, max_length = spec

    # Empty string → null (clear). Trim incidental whitespace
    # so a trailing newline from the operator's input doesn't
    # get persisted.
    cleaned: str | None = body.value
    if cleaned is not None:
        cleaned = cleaned.strip() or None
    if cleaned is not None and max_length is not None and len(cleaned) > max_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"value exceeds max_length={max_length} for "
                    f"field={body.field.value}"
                ),
                "errorCode": "value_too_long",
            },
        )
    # Title is required at the schema level (NOT NULL) — clearing
    # it would 500 in the DB. Reject upfront with a useful
    # message.
    if body.field is ProviderField.TITLE and cleaned is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "title cannot be cleared",
                "errorCode": "title_required",
            },
        )

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

    setattr(row, column_name, cleaned)

    if body.auto_lock:
        # Auto-lock so the next refresh respects the operator's
        # edit. The locked-fields list stays sorted+deduped just
        # like in the slice-146 surface.
        current = set(row.locked_fields or [])
        current.add(body.field.value)
        row.locked_fields = sorted(current)

    await db.commit()
    await db.refresh(row)
    return GameRead.model_validate(row, from_attributes=True)


@router.put(
    "/{game_id}/notes",
    response_model=GameRead,
    summary=(
        "Replace the operator-owned free-text notes for a Game "
        "(admin only). Notes are never touched by the metadata "
        "aggregator, distinct from the provider-owned summary."
    ),
)
async def put_notes(
    game_id: int,
    body: Annotated[NotesUpdateRequest, Body()],
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

    # Empty string + whitespace-only → null so reads have a
    # canonical "no notes" representation.
    cleaned = body.notes
    if cleaned is not None:
        cleaned = cleaned.strip() or None
    row.notes = cleaned

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
