"""IndexerRegistry tests (T043, T044)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers import IndexerRegistry
from romarr.indexers.models import Indexer
from romarr.metadata.encryption import encrypt


@pytest.fixture(autouse=True)
def _patch_secret_key(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every registry test needs a stable encryption key."""
    from romarr.config.settings import get_settings

    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_loads_only_enabled_indexers(
    async_session: AsyncSession,
) -> None:
    """T043: an indexer with every enable-* flag False is excluded."""
    async_session.add_all(
        [
            Indexer(
                name="A",
                implementation="newznab",
                url="https://a.test/api",
                source="manual",
                enable_rss=True,
                enable_automatic_search=True,
                enable_interactive_search=True,
            ),
            Indexer(
                name="B",
                implementation="newznab",
                url="https://b.test/api",
                source="manual",
                enable_rss=False,
                enable_automatic_search=False,
                enable_interactive_search=False,
            ),
        ]
    )
    await async_session.commit()

    registry = IndexerRegistry()
    clients = await registry.load_enabled(async_session)
    names = sorted(c.name for c in clients)
    assert names == ["A"]


@pytest.mark.asyncio
async def test_decrypts_api_key(async_session: AsyncSession) -> None:
    """T044: ``api_key_encrypted`` round-trips through ``encrypt`` and
    the in-memory client carries the plaintext."""
    plaintext = "secret-key-12345"
    blob = encrypt(json.dumps(plaintext).encode("utf-8"))

    async_session.add(
        Indexer(
            name="Encrypted",
            implementation="newznab",
            url="https://enc.test/api",
            api_key_encrypted=blob,
            source="manual",
        )
    )
    await async_session.commit()

    registry = IndexerRegistry()
    clients = await registry.load_enabled(async_session)
    assert len(clients) == 1
    assert clients[0].api_key == plaintext


@pytest.mark.asyncio
async def test_get_returns_none_for_missing(
    async_session: AsyncSession,
) -> None:
    registry = IndexerRegistry()
    assert await registry.get(async_session, indexer_id=9_999) is None


@pytest.mark.asyncio
async def test_rate_limiter_cached_across_calls(
    async_session: AsyncSession,
) -> None:
    """The same indexer id reuses one RateLimiter / one CircuitBreaker
    so gap-enforcement state survives across registry calls."""
    async_session.add(
        Indexer(
            name="Cached",
            implementation="newznab",
            url="https://cached.test/api",
            source="manual",
            rate_limit_seconds=5,
        )
    )
    await async_session.commit()

    registry = IndexerRegistry()
    a = await registry.load_enabled(async_session)
    b = await registry.load_enabled(async_session)
    # Both NewznabClients share the same limiter + breaker objects.
    assert a[0]._rate_limiter is b[0]._rate_limiter  # type: ignore[attr-defined]
    assert a[0]._breaker is b[0]._breaker  # type: ignore[attr-defined]
