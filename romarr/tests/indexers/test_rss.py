"""RSS sync orchestrator tests (T064-T066)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers import IndexerRegistry, IndexerRssSync
from romarr.indexers.models import Indexer
from romarr.metadata.encryption import encrypt


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    from romarr.config.settings import get_settings

    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed_indexers(
    session: AsyncSession,
) -> tuple[Indexer, Indexer, Indexer]:
    a = Indexer(
        name="A",
        implementation="newznab",
        url="https://a.test",
        source="manual",
        enable_rss=True,
        api_key_encrypted=encrypt(json.dumps("k").encode()),
    )
    b = Indexer(
        name="B",
        implementation="newznab",
        url="https://b.test",
        source="manual",
        enable_rss=True,
        api_key_encrypted=encrypt(json.dumps("k").encode()),
    )
    c = Indexer(
        name="C",
        implementation="newznab",
        url="https://c.test",
        source="manual",
        enable_rss=False,  # NOT in the sync_all set
        api_key_encrypted=encrypt(json.dumps("k").encode()),
    )
    session.add_all([a, b, c])
    await session.commit()
    for row in (a, b, c):
        await session.refresh(row)
    return a, b, c


_EMPTY_RSS = b"<?xml version='1.0'?><rss><channel/></rss>"


@pytest.mark.asyncio
async def test_sync_all_iterates_only_rss_enabled(
    async_session: AsyncSession,
) -> None:
    """T064: ``sync_all_enabled_indexers`` calls only the rss-enabled set."""
    await _seed_indexers(async_session)

    a_called = b_called = c_called = 0

    async with httpx.AsyncClient() as transport:
        registry = IndexerRegistry(http_client=transport)
        sync = IndexerRssSync(registry)
        with respx.mock:
            def _a(_request: httpx.Request) -> httpx.Response:
                nonlocal a_called
                a_called += 1
                return httpx.Response(200, content=_EMPTY_RSS)

            def _b(_request: httpx.Request) -> httpx.Response:
                nonlocal b_called
                b_called += 1
                return httpx.Response(200, content=_EMPTY_RSS)

            def _c(_request: httpx.Request) -> httpx.Response:
                nonlocal c_called
                c_called += 1
                return httpx.Response(200, content=_EMPTY_RSS)

            respx.get("https://a.test/api").mock(side_effect=_a)
            respx.get("https://b.test/api").mock(side_effect=_b)
            respx.get("https://c.test/api").mock(side_effect=_c)

            results = await sync.sync_all_enabled_indexers(async_session)

    assert len(results) == 2
    assert a_called >= 1
    assert b_called >= 1
    assert c_called == 0


@pytest.mark.asyncio
async def test_sync_indexer_isolated(
    async_session: AsyncSession,
) -> None:
    """T065: ``sync_indexer(id)`` only touches that one."""
    a, _b, _c = await _seed_indexers(async_session)

    async with httpx.AsyncClient() as transport:
        registry = IndexerRegistry(http_client=transport)
        sync = IndexerRssSync(registry)
        with respx.mock:
            route_a = respx.get("https://a.test/api").mock(
                return_value=httpx.Response(200, content=_EMPTY_RSS)
            )
            route_b = respx.get("https://b.test/api").mock(
                return_value=httpx.Response(200, content=_EMPTY_RSS)
            )
            result = await sync.sync_indexer(async_session, indexer_id=a.id)

    assert result is not None
    assert result.indexer_id == a.id
    assert route_a.called
    assert not route_b.called


@pytest.mark.asyncio
async def test_failures_do_not_propagate(
    async_session: AsyncSession,
) -> None:
    """T066: one indexer's 503 doesn't cancel the other; the failing
    indexer gets a health-issue row."""
    a, b, _c = await _seed_indexers(async_session)

    async with httpx.AsyncClient() as transport:
        registry = IndexerRegistry(http_client=transport)
        sync = IndexerRssSync(registry)
        with respx.mock:
            respx.get("https://a.test/api").mock(
                return_value=httpx.Response(200, content=_EMPTY_RSS)
            )
            respx.get("https://b.test/api").mock(
                return_value=httpx.Response(503)
            )
            results = await sync.sync_all_enabled_indexers(async_session)

    # Only the healthy one's RssResult comes back.
    indexer_ids = {r.indexer_id for r in results}
    assert a.id in indexer_ids
    assert b.id not in indexer_ids

    # The failing one's health row is stamped.
    row = (
        await async_session.execute(
            select(Indexer).where(Indexer.id == b.id)
        )
    ).scalar_one()
    assert row.last_health_ok is False
    assert row.last_health_error is not None


@pytest.mark.asyncio
async def test_sync_indexer_unknown_returns_none(
    async_session: AsyncSession,
) -> None:
    sync = IndexerRssSync()
    result = await sync.sync_indexer(async_session, indexer_id=9_999)
    assert result is None
