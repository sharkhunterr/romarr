"""DAT-sources read-only summary — /api/v3/dat-source.

Aggregates the DAT cache (``dat_entry`` table) by ``source`` so the
Settings > DAT Sources UI page (spec 014 T106) shows the operator
which authoritative DAT databases are loaded, how many entries each
contributes, how many platforms each covers, and the most-recent
ingestion timestamp.

Editing / re-ingestion is driven by the Tasks > Scheduler /dat-update
runner; this endpoint is the read surface only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.domain.models import DatEntry


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatSourceSummary(_Base):
    """One row per distinct ``DatEntry.source`` value."""

    source: str
    entry_count: int
    platform_count: int
    latest_updated_at: datetime | None


router = APIRouter(prefix="/api/v3/dat-source", tags=["DAT Sources"])


@router.get(
    "",
    response_model=list[DatSourceSummary],
    summary="DAT cache summary grouped by source (any authenticated user).",
)
async def list_dat_sources(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DatSourceSummary]:
    """One row per distinct ``DatEntry.source`` (No-Intro / Redump
    / TOSEC / etc.), with entry count, platform count, and the
    most-recent ``updated_at`` across the source's rows. Sorted
    by source name for deterministic UI rendering.
    """
    rows = (
        await db.execute(
            select(
                DatEntry.source,
                func.count(DatEntry.id).label("entry_count"),
                func.count(distinct(DatEntry.platform_id)).label(
                    "platform_count"
                ),
                func.max(DatEntry.updated_at).label("latest_updated_at"),
            )
            .group_by(DatEntry.source)
            .order_by(DatEntry.source.asc())
        )
    ).all()

    return [
        DatSourceSummary(
            source=row.source,
            entry_count=int(row.entry_count),
            platform_count=int(row.platform_count),
            latest_updated_at=row.latest_updated_at,
        )
        for row in rows
    ]
