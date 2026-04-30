"""Indexer health-issue persistence (Phase 9 RSSHEALTH).

``record_health_issue`` writes the indexer row's
``last_health_at`` / ``last_health_ok`` / ``last_health_error``
columns; ``clear_health`` resets them on next success.

The /api/v3/health endpoint that surfaces these to operators lives
in the Notifications spec; this module only persists the data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.indexers.models import Indexer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.indexers.types import IndexerHealthIssue

logger = logging.getLogger(__name__)


async def record_health_issue(
    session: AsyncSession,
    issue: IndexerHealthIssue,
    *,
    commit: bool = True,
) -> None:
    """Stamp ``issue`` onto the indexer row's health columns.

    ``commit=False`` skips the commit and leaves it to the caller —
    used by :class:`IndexerRssSync` whose ``asyncio.gather`` parallel
    fan-out can't run concurrent commits on a shared session
    (SQLAlchemy raises ``IllegalStateChangeError``).
    """
    row = (
        await session.execute(
            select(Indexer).where(Indexer.id == issue.indexer_id)
        )
    ).scalar_one_or_none()
    if row is None:
        logger.warning(
            "indexers.health.unknown_indexer",
            extra={"indexer_id": issue.indexer_id, "category": issue.category},
        )
        return
    row.last_health_at = issue.occurred_at
    row.last_health_ok = False
    row.last_health_error = f"{issue.category}: {issue.message}"
    if commit:
        await session.commit()


async def clear_health(
    session: AsyncSession, *, indexer_id: int, commit: bool = True
) -> None:
    """Reset the indexer row's health to OK on next success."""
    row = (
        await session.execute(
            select(Indexer).where(Indexer.id == indexer_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.last_health_at = datetime.now(UTC)
    row.last_health_ok = True
    row.last_health_error = None
    if commit:
        await session.commit()


__all__ = ["clear_health", "record_health_issue"]
