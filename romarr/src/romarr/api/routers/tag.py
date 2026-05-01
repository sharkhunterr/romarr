"""Tag CRUD + assignment-detail endpoints (T060, FR per spec 013 Q5).

Spec 013 ships polymorphic tags: a global :class:`Tag` table plus
the polymorphic :class:`TagAssignment` association table whose
``entity_type`` is one of the four documented strings
(``game``, ``indexer``, ``notification``, ``release``).

The routes mirror Sonarr's `/api/v3/tag*` shape so the same
ecosystem-tooling patterns apply:

  * ``GET    /api/v3/tag``                 list every tag (flat)
  * ``POST   /api/v3/tag``                 create a tag (admin)
  * ``GET    /api/v3/tag/{id}``            read one tag
  * ``PUT    /api/v3/tag/{id}``            update one tag (admin)
  * ``DELETE /api/v3/tag/{id}``            delete one tag (admin);
    HTTP 409 if the tag is in use unless the caller passes
    ``?force=true`` — that path also cascades the
    ``tag_assignment`` rows.
  * ``GET    /api/v3/tag/detail/{id}``     show every entity
    using the tag, grouped by entity_type.

The list endpoint is intentionally NOT paginated: tag catalogues
stay in the dozens, even for power users, and Sonarr's contract
returns a flat array. If a future operator scales past a few
hundred tags, the canonical pagination wrapper from
:mod:`romarr.api.pagination` slots in cleanly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import (
    get_db,
    require_admin,
    require_readonly,
)
from romarr.api.models import DEFAULT_TAG_COLOR, Tag, TagAssignment
from romarr.auth import Principal

router = APIRouter(prefix="/api/v3/tag", tags=["Tag"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class CreateTagRequest(_Base):
    name: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    ]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    color: Annotated[
        str, Field(pattern=_HEX_COLOR_PATTERN)
    ] = DEFAULT_TAG_COLOR


class UpdateTagRequest(_Base):
    label: Annotated[str | None, Field(max_length=128)] = None
    color: Annotated[str | None, Field(pattern=_HEX_COLOR_PATTERN)] = None


class TagRead(_Base):
    id: int
    name: str
    label: str
    color: str


class TagDetail(_Base):
    """Sonarr `/tag/detail/{id}` shape — lists the IDs of every
    entity currently using the tag, grouped by entity type. The
    JSON keys are camelCase (``gameIds`` / ``indexerIds`` / ...)
    via Pydantic aliases."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
        # Serialize with the camelCase aliases by default —
        # FastAPI applies ``response_model_by_alias=True`` per-route
        # below, but pinning it on the schema keeps any future
        # ``model_dump()`` callers honest.
    )

    id: int
    label: str
    game_ids: list[int] = Field(alias="gameIds")
    indexer_ids: list[int] = Field(alias="indexerIds")
    notification_ids: list[int] = Field(alias="notificationIds")
    release_ids: list[int] = Field(alias="releaseIds")


def _to_read(tag: Tag) -> TagRead:
    return TagRead(
        id=tag.id, name=tag.name, label=tag.label, color=tag.color
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[TagRead],
    summary="List every tag.",
)
async def list_tags(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TagRead]:
    rows = (
        await db.execute(select(Tag).order_by(Tag.name))
    ).scalars().all()
    return [_to_read(row) for row in rows]


@router.post(
    "",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tag (admin).",
)
async def create_tag(
    payload: CreateTagRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagRead:
    tag = Tag(
        name=payload.name, label=payload.label, color=payload.color
    )
    db.add(tag)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": (
                    f"a tag with name {payload.name!r} already exists"
                ),
                "errorCode": "tag_name_conflict",
            },
        ) from exc
    await db.refresh(tag)
    return _to_read(tag)


async def _get_tag_or_404(db: AsyncSession, tag_id: int) -> Tag:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "tag_not_found", "errorCode": "not_found"},
        )
    return tag


@router.get(
    "/detail/{tag_id}",
    response_model=TagDetail,
    response_model_by_alias=True,
    summary="Show every entity currently tagged with this id.",
)
async def tag_detail(
    tag_id: int,
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagDetail:
    tag = await _get_tag_or_404(db, tag_id)
    rows = (
        await db.execute(
            select(TagAssignment).where(TagAssignment.tag_id == tag_id)
        )
    ).scalars().all()
    grouped: dict[str, list[int]] = {
        "game": [],
        "indexer": [],
        "notification": [],
        "release": [],
    }
    for assignment in rows:
        bucket = grouped.get(assignment.entity_type)
        if bucket is not None:
            bucket.append(assignment.entity_id)
    return TagDetail(
        id=tag.id,
        label=tag.label,
        game_ids=sorted(grouped["game"]),
        indexer_ids=sorted(grouped["indexer"]),
        notification_ids=sorted(grouped["notification"]),
        release_ids=sorted(grouped["release"]),
    )


@router.get(
    "/{tag_id}",
    response_model=TagRead,
    summary="Read one tag by id.",
)
async def read_tag(
    tag_id: int,
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagRead:
    tag = await _get_tag_or_404(db, tag_id)
    return _to_read(tag)


@router.put(
    "/{tag_id}",
    response_model=TagRead,
    summary="Update one tag's label or colour (admin).",
)
async def update_tag(
    tag_id: int,
    payload: UpdateTagRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagRead:
    tag = await _get_tag_or_404(db, tag_id)
    if payload.label is not None:
        tag.label = payload.label
    if payload.color is not None:
        tag.color = payload.color
    await db.commit()
    await db.refresh(tag)
    return _to_read(tag)


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Delete one tag (admin). Returns HTTP 409 if the tag is "
        "currently assigned to any entity unless ?force=true is set, "
        "in which case the assignments are cascaded."
    ),
)
async def delete_tag(
    tag_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: Annotated[
        bool,
        Query(description="Cascade-delete any TagAssignment rows."),
    ] = False,
) -> None:
    tag = await _get_tag_or_404(db, tag_id)

    in_use_q = select(TagAssignment).where(TagAssignment.tag_id == tag_id)
    in_use = (await db.execute(in_use_q)).scalars().first()
    if in_use is not None and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": (
                    f"tag {tag.name!r} is in use; pass ?force=true to "
                    "cascade-delete the assignments"
                ),
                "errorCode": "tag_in_use",
            },
        )

    if force and in_use is not None:
        await db.execute(
            delete(TagAssignment).where(TagAssignment.tag_id == tag_id)
        )

    await db.delete(tag)
    await db.commit()


__all__ = ["router"]
