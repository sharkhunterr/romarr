"""RSS sync orchestrator (Phase 9 RSSHEALTH).

``IndexerRssSync.sync_all_enabled_indexers()`` drives ``rss()`` on
every indexer that has ``enable_rss = True``. Failures are isolated
via :func:`asyncio.gather(..., return_exceptions=True)` (FR-019a):
one bad indexer never cancels its siblings, the parser-error /
auth-error / protocol-error is captured as an
:class:`IndexerHealthIssue` and persisted via :mod:`health`, and
the surviving indexers' results come back to the caller.

The Tasks/Scheduler spec consumes ``sync_all_enabled_indexers`` on
a cron — this module doesn't schedule itself.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.indexers.health import clear_health, record_health_issue
from romarr.indexers.models import Indexer
from romarr.indexers.registry import IndexerRegistry
from romarr.indexers.types import IndexerHealthIssue, RssResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.indexers.client import NewznabClient

logger = logging.getLogger(__name__)


class IndexerRssSync:
    """RSS-sync façade. Holds a registry instance for caching."""

    def __init__(self, registry: IndexerRegistry | None = None) -> None:
        self._registry = registry or IndexerRegistry()

    async def sync_all_enabled_indexers(
        self, session: AsyncSession
    ) -> list[RssResult]:
        """Run ``rss()`` on every ``enable_rss=True`` indexer in parallel.

        Returns one :class:`RssResult` per success. Failures are
        captured and persisted but never raise.
        """
        rows = (
            (
                await session.execute(
                    select(Indexer).where(Indexer.enable_rss.is_(True))
                )
            )
            .scalars()
            .all()
        )

        clients: list[NewznabClient] = [
            self._registry._build_client(row) for row in rows
        ]

        results = await asyncio.gather(
            *(self._sync_one(session, c) for c in clients),
            return_exceptions=True,
        )
        # Concurrent commits on a shared AsyncSession trigger
        # ``IllegalStateChangeError``; per-task health writes use
        # ``commit=False`` and we commit once after the gather.
        await session.commit()

        return [r for r in results if isinstance(r, RssResult)]

    async def sync_indexer(
        self, session: AsyncSession, *, indexer_id: int
    ) -> RssResult | None:
        """Run ``rss()`` on a single indexer; returns the result or None
        on failure (the failure is recorded as a health issue)."""
        client = await self._registry.get(session, indexer_id=indexer_id)
        if client is None:
            return None
        outcome = await self._sync_one(session, client)
        # The single-indexer path doesn't have the gather-collision
        # problem, so we commit here.
        await session.commit()
        return outcome if isinstance(outcome, RssResult) else None

    async def _sync_one(
        self, session: AsyncSession, client: NewznabClient
    ) -> RssResult | Exception:
        started = datetime.now(UTC)
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        try:
            items = await client.rss()
        except Exception as exc:
            logger.warning(
                "indexers.rss.failed",
                extra={
                    "indexer_id": client.indexer_id,
                    "indexer_name": client.name,
                    "exc_type": type(exc).__name__,
                    "exc_str": str(exc),
                },
            )
            await record_health_issue(
                session,
                IndexerHealthIssue(
                    indexer_id=client.indexer_id,
                    indexer_name=client.name,
                    category="protocol",
                    message=str(exc),
                    occurred_at=started,
                ),
                commit=False,
            )
            return exc
        elapsed_ms = int((loop.time() - t0) * 1000)

        # Stage health writes; the parent commits once after gather.
        for issue in client.health_issues:
            await record_health_issue(session, issue, commit=False)
        if not client.health_issues:
            await clear_health(session, indexer_id=client.indexer_id, commit=False)

        return RssResult(
            indexer_id=client.indexer_id,
            items=items,
            fetched_at=started,
            elapsed_ms=elapsed_ms,
        )


__all__ = ["IndexerRssSync"]
