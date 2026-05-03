"""Game + Release read + lock + per-field edit + notes + bulk
endpoints (slices 86, 146, 147, 149, 151, 153, 154, 164).

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, and_, asc, cast, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.api.models import Tag, TagAssignment
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


class BulkMonitorRequest(BaseModel):
    """POST /api/v3/game/bulk-monitor — flip the monitored flag
    on a batch of Games.

    Powers the Library page's bulk-select action bar (slice
    152). Capped at 500 ids per request so an accidental
    "select everything" doesn't lock up the DB; the UI shards
    larger selections client-side.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    game_ids: Annotated[
        list[int],
        Field(alias="gameIds", min_length=1, max_length=500),
    ]
    monitored: bool


class BulkMonitorResponse(BaseModel):
    """Response envelope for the bulk-monitor endpoint.

    ``updated`` is the count of rows actually flipped. Rows
    whose ``monitored`` flag was already at the requested value
    are still counted as "updated" — the operator's intent
    (idempotent set) is what matters here. ``missing`` lists
    any ids the operator passed that didn't resolve to a Game.
    """

    model_config = ConfigDict(extra="forbid")

    updated: int
    missing: list[int]


class BulkDeleteRequest(BaseModel):
    """POST /api/v3/game/bulk-delete — destroy a batch of Games.

    Per the constitution Romarr never auto-deletes ROM files on
    disk; this surface only removes the database row (and its
    Releases / Dumps via cascade). Operators choose whether on-
    disk cleanup happens via the per-library lifecycle policy.

    Capped at 500 ids per call so an accidental "select all"
    can't run away. The UI shards larger selections client-side
    and gates the confirm button with a 1-second delay per
    the spec's destructive-action discipline.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    game_ids: Annotated[
        list[int],
        Field(alias="gameIds", min_length=1, max_length=500),
    ]


class BulkDeleteResponse(BaseModel):
    """Response envelope for the bulk-delete endpoint."""

    model_config = ConfigDict(extra="forbid")

    deleted: int
    missing: list[int]


class BulkTagRequest(BaseModel):
    """POST /api/v3/game/bulk-tag — slice 154.

    Apply or strip a set of tags across a batch of Games. The
    ``Game.tags`` JSON column stores tag ids; this surface
    canonicalises the per-row list (sorted, deduped) on every
    write so the JSON shape stays stable.

    ``action="add"`` unions the supplied tag ids into each
    Game's existing list. ``action="remove"`` strips them.
    Capped at 500 ids per call; the operator can run a second
    pass for larger selections.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    game_ids: Annotated[
        list[int],
        Field(alias="gameIds", min_length=1, max_length=500),
    ]
    tag_ids: Annotated[
        list[int],
        Field(alias="tagIds", min_length=1, max_length=50),
    ]
    action: Literal["add", "remove"]


class BulkTagResponse(BaseModel):
    """Response envelope for the bulk-tag endpoint."""

    model_config = ConfigDict(extra="forbid")

    updated: int
    missing: list[int]


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
    tag_id: Annotated[
        int | None,
        Query(
            ge=1,
            description=(
                "Restrict to games carrying a specific tag id. "
                "Matched against the Game.tags JSON list."
            ),
        ),
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
    if tag_id is not None:
        # Game.tags is a JSON list of int. To match "list contains
        # tag_id" portably across SQLite + Postgres we cast the
        # JSON to text, normalise the delimiters (replace ``[``
        # and ``]`` with ``,``, drop whitespace), then look for
        # ``,<id>,``. This survives both compact (`[1,2]`) and
        # spaced (`[1, 2]`) serialisations and rejects the
        # ``[15]`` vs id=5 false-match.
        normalised = func.replace(
            func.replace(
                func.replace(cast(Game.tags, String), " ", ""),
                "[",
                ",",
            ),
            "]",
            ",",
        )
        stmt = stmt.where(normalised.like(f"%,{tag_id},%"))
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


@router.post(
    "/bulk-monitor",
    response_model=BulkMonitorResponse,
    summary=(
        "Flip the monitored flag on a batch of games (admin "
        "only). Capped at 500 ids per call. Returns the number "
        "of rows updated and the ids that didn't resolve."
    ),
)
async def bulk_monitor(
    body: Annotated[BulkMonitorRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkMonitorResponse:
    rows = (
        (
            await db.execute(
                select(Game).where(Game.id.in_(body.game_ids))
            )
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = sorted(set(body.game_ids) - found)
    for row in rows:
        row.monitored = body.monitored
    await db.commit()
    return BulkMonitorResponse(updated=len(rows), missing=missing)


@router.post(
    "/bulk-delete",
    response_model=BulkDeleteResponse,
    summary=(
        "Delete a batch of Games — and their Releases / Dumps "
        "via cascade — without touching ROM files on disk "
        "(admin only). Capped at 500 ids per call. Per the "
        "constitution, on-disk cleanup is the per-library "
        "lifecycle policy's job, not this endpoint's."
    ),
)
async def bulk_delete(
    body: Annotated[BulkDeleteRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkDeleteResponse:
    rows = (
        (
            await db.execute(
                select(Game).where(Game.id.in_(body.game_ids))
            )
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = sorted(set(body.game_ids) - found)
    for row in rows:
        # Cascading delete-orphan on Game.releases handles the
        # downstream Release + Dump rows; the FK onDelete on
        # Dump is also CASCADE so this stays atomic.
        await db.delete(row)
    await db.commit()
    return BulkDeleteResponse(deleted=len(rows), missing=missing)


@router.post(
    "/bulk-tag",
    response_model=BulkTagResponse,
    summary=(
        "Add or remove a set of tags across a batch of Games "
        "(admin only). Capped at 500 game ids and 50 tag ids "
        "per call. The per-row tag list is canonicalised "
        "(sorted, deduped) on every write."
    ),
)
async def bulk_tag(
    body: Annotated[BulkTagRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkTagResponse:
    # Pre-validate tag ids against the Tag catalogue so a
    # bogus ``tagIds`` payload 400s cleanly instead of 500-ing
    # on the FK INSERT slice 164 added below.
    existing_tag_ids = set(
        (
            await db.execute(
                select(Tag.id).where(Tag.id.in_(body.tag_ids))
            )
        )
        .scalars()
        .all()
    )
    missing_tags = sorted(set(body.tag_ids) - existing_tag_ids)
    if missing_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"unknown tag_ids: {missing_tags}"
                ),
                "errorCode": "unknown_tag_ids",
            },
        )

    rows = (
        (
            await db.execute(
                select(Game).where(Game.id.in_(body.game_ids))
            )
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = sorted(set(body.game_ids) - found)
    tag_set = set(body.tag_ids)
    for row in rows:
        current = set(row.tags or [])
        if body.action == "add":
            current |= tag_set
        else:  # "remove"
            current -= tag_set
        # JSON columns need a fresh list assignment for SQLAlchemy
        # to detect the mutation; sorted output keeps the JSON
        # shape stable across runs.
        row.tags = sorted(current)

    # Slice 164: keep the polymorphic ``tag_assignment`` rows in
    # sync with the JSON cache so the slice-135 ``usageCount``
    # surface on the Tags page stays accurate. Read existing
    # assignments for the affected (tag_id, entity_id) pairs to
    # avoid violating the ``uq_tag_assignment_unique`` constraint
    # on a re-add.
    if found:
        if body.action == "add":
            existing = {
                (row.tag_id, row.entity_id)
                for row in (
                    await db.execute(
                        select(TagAssignment).where(
                            TagAssignment.entity_type == "game",
                            TagAssignment.entity_id.in_(found),
                            TagAssignment.tag_id.in_(body.tag_ids),
                        )
                    )
                ).scalars().all()
            }
            new_assignments = [
                TagAssignment(
                    tag_id=tag_id,
                    entity_type="game",
                    entity_id=entity_id,
                )
                for entity_id in found
                for tag_id in body.tag_ids
                if (tag_id, entity_id) not in existing
            ]
            db.add_all(new_assignments)
        else:  # "remove"
            await db.execute(
                delete(TagAssignment).where(
                    and_(
                        TagAssignment.entity_type == "game",
                        TagAssignment.entity_id.in_(found),
                        TagAssignment.tag_id.in_(body.tag_ids),
                    )
                )
            )

    await db.commit()
    return BulkTagResponse(updated=len(rows), missing=missing)


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
