"""Cache helper tests (T031-T034)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.search.cache import (
    cache_key_for,
    get_cached,
    invalidate,
    put_cached,
)
from romarr.search.models import SearchCache


async def _make_indexer(session: AsyncSession) -> Indexer:
    indexer = Indexer(
        name="Test",
        implementation="newznab",
        url="https://idx.test/api",
        categories=[1060],
        source="manual",
    )
    session.add(indexer)
    await session.commit()
    await session.refresh(indexer)
    return indexer


# ---------------------------------------------------------------------------
# cache_key_for: deterministic + insensitive to category order
# ---------------------------------------------------------------------------


def test_cache_key_deterministic() -> None:
    a = cache_key_for("Sonic", [1060, 7010])
    b = cache_key_for("sonic", [7010, 1060])
    assert a == b


def test_cache_key_strips_query_whitespace() -> None:
    a = cache_key_for("  Sonic  ", [1060])
    b = cache_key_for("sonic", [1060])
    assert a == b


def test_cache_key_differs_by_category_set() -> None:
    a = cache_key_for("Sonic", [1060])
    b = cache_key_for("Sonic", [1060, 7010])
    assert a != b


# ---------------------------------------------------------------------------
# T031 — cache hit inside TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_inside_ttl(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    now = datetime.now(UTC)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "abc", "title": "Sonic the Hedgehog (USA)"}],
        ttl_seconds=3600,
        now=now,
    )

    hit = await get_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        now=now + timedelta(seconds=300),
    )
    assert hit is not None
    assert hit["results"][0]["guid"] == "abc"


# ---------------------------------------------------------------------------
# T032 — cache miss past TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_after_ttl(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    now = datetime.now(UTC)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "abc"}],
        ttl_seconds=60,
        now=now,
    )

    expired = await get_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        now=now + timedelta(seconds=120),
    )
    assert expired is None


# ---------------------------------------------------------------------------
# T033 — RSS bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rss_bypasses_cache(async_session: AsyncSession) -> None:
    """``bypass=True`` always misses regardless of stored state (FR-027)."""
    indexer = await _make_indexer(async_session)
    now = datetime.now(UTC)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "abc"}],
        ttl_seconds=3600,
        now=now,
    )

    miss = await get_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        now=now,
        bypass=True,
    )
    assert miss is None


# ---------------------------------------------------------------------------
# T034 — orphaned-indexer cache row treated as miss after CASCADE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_row_cascades_on_indexer_delete(
    async_session: AsyncSession,
) -> None:
    """Deleting the indexer wipes its cache rows via ON DELETE CASCADE,
    so subsequent lookups treat them as miss (FR-028)."""
    indexer = await _make_indexer(async_session)
    now = datetime.now(UTC)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "abc"}],
        ttl_seconds=3600,
        now=now,
    )

    await async_session.delete(indexer)
    await async_session.commit()

    rows = (await async_session.execute(select(SearchCache))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# put_cached overwrites when the key already exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_cached_overwrites_existing(
    async_session: AsyncSession,
) -> None:
    indexer = await _make_indexer(async_session)
    now = datetime.now(UTC)

    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "first"}],
        now=now,
    )
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[{"guid": "second"}],
        now=now + timedelta(seconds=10),
    )

    rows = (await async_session.execute(select(SearchCache))).scalars().all()
    assert len(rows) == 1
    assert rows[0].parsed_results[0]["guid"] == "second"


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_removes_row(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    await put_cached(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
        response_xml=b"<rss/>",
        parsed_results=[],
    )
    deleted = await invalidate(
        async_session,
        indexer_id=indexer.id,
        query="Sonic",
        category_ids=[1060],
    )
    assert deleted == 1


@pytest.mark.asyncio
async def test_invalidate_unknown_key_returns_zero(
    async_session: AsyncSession,
) -> None:
    indexer = await _make_indexer(async_session)
    deleted = await invalidate(
        async_session,
        indexer_id=indexer.id,
        query="never-cached",
        category_ids=[1],
    )
    assert deleted == 0
