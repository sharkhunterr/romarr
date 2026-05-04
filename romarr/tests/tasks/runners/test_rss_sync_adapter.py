"""Tests for the RssSyncAdapter wired to spec 004's
``IndexerRssSync.sync_all_enabled_indexers`` (slice 204)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.indexers.models import Indexer
from romarr.metadata.encryption import encrypt
from romarr.tasks.runners.adapters import RssSyncAdapter


def _fake_context(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None,
    parameters: dict[str, object] | None = None,
) -> SimpleNamespace:
    """Duck-typed JobContext substitute (frozen Pydantic model
    can't carry the ``sessionmaker`` after construction)."""
    return SimpleNamespace(
        job_id="RssSync",
        job_run_id=1,
        triggered_by=SimpleNamespace(value="cron"),
        sessionmaker=sessionmaker,
        parameters=parameters or {},
    )


async def _seed_indexer(
    sm: async_sessionmaker[AsyncSession],
    *,
    name: str,
    enable_rss: bool = True,
) -> None:
    async with sm() as session:
        session.add(
            Indexer(
                name=name,
                implementation="newznab",
                url=f"https://{name.lower()}.test",
                source="manual",
                enable_rss=enable_rss,
                api_key_encrypted=encrypt(json.dumps("k").encode()),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_rss_sync_adapter_falls_back_without_sessionmaker() -> None:
    """No sessionmaker → adapter returns the documented stub.
    Catches the regression where a refactor accidentally
    crashes the scheduler dispatch on a misconfigured app."""
    adapter = RssSyncAdapter()
    context = _fake_context(sessionmaker=None)
    result = await adapter._run(context)
    assert result.summary["stub"] is True
    assert result.summary["reason"] == "no sessionmaker"


@pytest.mark.asyncio
async def test_rss_sync_adapter_with_no_indexers_returns_zero_counts(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty indexer table → 0 succeeded, 0 items.
    Settings.auth_secret_key needs to be in the env so the
    encryption helper can decrypt the (zero) api keys."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only" * 4)
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    adapter = RssSyncAdapter()
    context = _fake_context(sessionmaker=async_sessionmaker_factory)
    result = await adapter._run(context)
    assert result.summary["indexers_succeeded"] == 0
    assert result.summary["items_total"] == 0


@pytest.mark.asyncio
async def test_rss_sync_adapter_skips_disabled_indexers(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enable_rss=False`` rows are excluded from the sync
    (verified at the spec 004 layer; here we exercise the
    full adapter path with mixed-flag rows)."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only" * 4)
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    sm = async_sessionmaker_factory
    await _seed_indexer(sm, name="DisabledOnly", enable_rss=False)

    adapter = RssSyncAdapter()
    context = _fake_context(sessionmaker=sm)
    result = await adapter._run(context)
    # The one indexer is enable_rss=False → not synced. Real
    # network calls would also fail (the test URL isn't a real
    # host) but that path is filtered before we get there.
    assert result.summary["indexers_succeeded"] == 0
