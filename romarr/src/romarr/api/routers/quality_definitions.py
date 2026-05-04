"""Quality-definitions read-only summary — /api/v3/quality-definition.

The Settings > Quality Definitions UI page (spec 014 T106) lists
per-platform file size bounds at a glance. Each ``PlatformFormat``
row carries the ``min_size_bytes`` / ``max_size_bytes`` floor + ceiling
the search engine + importer use to reject re-encodes that fall
outside the expected range (FR-008 / FR-021 / spec 007 quality).

The aggregated read endpoint flattens the ``Platform → PlatformFormat``
tree into one round-trip so the UI doesn't fan out N+1 fetches against
``/api/v3/rom/platform/{id}/format``. Editing still goes through the
existing admin-scoped CRUD on the platform router (FR-026a).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Platform, PlatformFormat


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class QualityDefinitionFormat(_Base):
    """One ``PlatformFormat`` row in the aggregated summary."""

    id: int
    extension: str
    format_type: str
    min_size_bytes: int | None
    max_size_bytes: int | None
    pack_source: str


class QualityDefinitionPlatform(_Base):
    """One platform with its formats nested."""

    platform_id: int
    platform_slug: str
    platform_name: str
    formats: list[QualityDefinitionFormat] = Field(default_factory=list)


router = APIRouter(
    prefix="/api/v3/quality-definition",
    tags=["Quality Definitions"],
)


@router.get(
    "",
    response_model=list[QualityDefinitionPlatform],
    summary="List per-platform format size bounds (any authenticated user).",
)
async def list_quality_definitions(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[QualityDefinitionPlatform]:
    """One row per Platform; ``formats`` lists every PlatformFormat
    with its min / max size bounds. Sorted alphabetically on
    platform name + format extension for deterministic UI rendering.
    """
    platforms = (
        (await db.execute(select(Platform).order_by(Platform.name.asc())))
        .scalars()
        .all()
    )
    formats = (
        (
            await db.execute(
                select(PlatformFormat).order_by(
                    PlatformFormat.platform_id.asc(),
                    PlatformFormat.extension.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    by_platform: dict[int, list[QualityDefinitionFormat]] = {}
    for f in formats:
        by_platform.setdefault(f.platform_id, []).append(
            QualityDefinitionFormat(
                id=f.id,
                extension=f.extension,
                format_type=f.format_type,
                min_size_bytes=f.min_size_bytes,
                max_size_bytes=f.max_size_bytes,
                pack_source=f.pack_source,
            )
        )

    return [
        QualityDefinitionPlatform(
            platform_id=p.id,
            platform_slug=p.slug,
            platform_name=p.name,
            formats=by_platform.get(p.id, []),
        )
        for p in platforms
    ]
