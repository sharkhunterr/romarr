"""Cache LRU eviction tests (spec 007 CL009 / FR-028a).

The production constants are 10_000 → 9_000 (1k row drop). For
unit-test speed we monkey-patch the constants down to 10 → 7 so
the eviction logic exercises the same shape with manageable
fixtures. The actual numbers are pinned by
``test_constants_match_spec`` so a future tweak to the cap can't
silently break the spec contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.search import cache as cache_mod
from romarr.search.cache import (
    CACHE_HARD_CAP,
    CACHE_LOW_WATER,
    get_cached,
    put_cached,
)
from romarr.search.models import SearchCache


async def _make_indexer(session: AsyncSession) -> Indexer:
    indexer = Indexer(
        name="LRU Test",
        implementation="newznab",
        url="https://idx.test/api",
        categories=[1060],
        source="manual",
    )
    session.add(indexer)
    await session.commit()
    await session.refresh(indexer)
    return indexer


def test_cache_constants_match_spec_007() -> None:
    """Pin the documented FR-028a values."""
    assert CACHE_HARD_CAP == 10_000
    assert CACHE_LOW_WATER == 9_000


@pytest.mark.asyncio
async def test_lru_eviction_trims_to_low_water(
    async_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past ``CACHE_HARD_CAP`` rows → bulk DELETE down to
    ``CACHE_LOW_WATER``. Eviction order is oldest
    ``last_read_at`` first."""
    monkeypatch.setattr(cache_mod, "CACHE_HARD_CAP", 10)
    monkeypatch.setattr(cache_mod, "CACHE_LOW_WATER", 7)

    indexer = await _make_indexer(async_session)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    # Seed 10 rows with staggered last_read_at so we know which
    # ones the eviction must drop. Row 0 is the oldest.
    for i in range(10):
        await put_cached(
            async_session,
            indexer_id=indexer.id,
            query=f"row-{i}",
            category_ids=[1060],
            response_xml=b"<rss/>",
            parsed_results=[{"i": i}],
            ttl_seconds=3600,
            now=base + timedelta(seconds=i),
        )

    # Insert one more — total becomes 11, eviction drains to 7.
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="row-trigger",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"i": "trigger"}],
        ttl_seconds=3600,
        now=base + timedelta(seconds=100),
    )

    count = (
        await async_session.execute(select(func.count(SearchCache.id)))
    ).scalar_one()
    assert count == 7, f"expected 7 rows after eviction, got {count}"

    # The oldest seeded queries (row-0 through row-3) must be gone.
    surviving_queries = sorted(
        (await async_session.execute(select(SearchCache.query))).scalars().all()
    )
    for dropped in ("row-0", "row-1", "row-2", "row-3"):
        assert dropped not in surviving_queries, (
            f"oldest query {dropped} should have been evicted"
        )
    # The newest (the trigger row) MUST survive.
    assert "row-trigger" in surviving_queries


@pytest.mark.asyncio
async def test_cache_hit_updates_last_read_at(
    async_session: AsyncSession,
) -> None:
    """A cache hit MUST refresh ``last_read_at`` so re-read rows
    don't get evicted before genuinely-cold rows. Without this,
    LRU would degenerate into FIFO."""
    indexer = await _make_indexer(async_session)
    inserted_at = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="hot-query",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"i": 0}],
        ttl_seconds=3600,
        now=inserted_at,
    )

    later = inserted_at + timedelta(minutes=10)
    hit = await get_cached(
        async_session,
        indexer_id=indexer.id,
        query="hot-query",
        category_ids=[1060],
        now=later,
    )
    assert hit is not None

    row = (
        await async_session.execute(
            select(SearchCache).where(SearchCache.query == "hot-query")
        )
    ).scalar_one()
    # SQLite drops tzinfo on round-trip; compare naive timestamps.
    later_naive = later.replace(tzinfo=None)
    assert row.last_read_at.replace(tzinfo=None) == later_naive
