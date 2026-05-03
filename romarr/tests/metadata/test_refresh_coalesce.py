"""Per-Game refresh coalescing (spec 002 CL010, FR-013a).

Two concurrent ``refresh_game_metadata(game_id=X)`` calls must
NOT each fire a fresh provider round. The first call holds the
per-Game lock, populates ``metadata_cache``, and releases. The
second call wakes, hits the cache, and skips the provider
fetch entirely. End result: provider quota burned exactly once
per concurrent burst.

This test pins the contract by counting calls into a fake
provider while running two refreshes via ``asyncio.gather``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Game, Platform
from romarr.metadata import refresh as refresh_mod
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import (
    GameMetadata,
    GameSearchResult,
    ProviderField,
)


class _CountingProvider(MetadataProvider):
    """Stub provider that returns a fixed payload + counts calls."""

    capabilities = ProviderCapabilities(
        name="igdb",  # must be in the enum allowlist
        requires_auth=False,
        contributable_fields=frozenset(
            {ProviderField.TITLE, ProviderField.SUMMARY}
        ),
        invoked_in_scan=True,
    )

    def __init__(self) -> None:
        super().__init__(rate_limit_rps=1000, rate_limit_burst=1000)
        self.search_calls = 0
        self.get_game_calls = 0

    def configure(self, config: dict[str, Any]) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        self.search_calls += 1
        # Tiny sleep so the second concurrent call has a chance
        # to queue on the lock rather than sneaking in before
        # the first call's cache write.
        await asyncio.sleep(0.05)
        return [
            GameSearchResult(
                provider_name="igdb",
                provider_game_id="igdb-1",
                title=query,
                confidence=0.95,
            )
        ]

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        self.get_game_calls += 1
        return GameMetadata(
            provider_name="igdb",
            provider_game_id=provider_game_id,
            fields={
                ProviderField.TITLE: "Sonic the Hedgehog",
                ProviderField.SUMMARY: "Spin spin spin.",
            },
            cover_url=None,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError

    def get_platform_mapping(self, platform_slug: str) -> int | str | None:
        return None


@pytest.mark.asyncio
async def test_concurrent_refreshes_call_provider_once(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two refreshes on the same Game burn one provider round."""
    sm = async_sessionmaker_factory

    # Reset the per-process lock registry — earlier tests may
    # have left a lock keyed on this game_id.
    refresh_mod._GAME_LOCKS.clear()

    async with sm() as setup:
        platform = Platform(slug="megadrive", name="Mega Drive")
        setup.add(platform)
        await setup.flush()
        game = Game(
            platform_id=platform.id,
            slug="sonic-1",
            title="Sonic the Hedgehog",
        )
        setup.add(game)
        await setup.commit()
        game_id = game.id

    counting = _CountingProvider()

    async def _fake_load_providers(session: Any, scan: bool = True):
        return [counting]

    monkeypatch.setattr(
        refresh_mod, "load_enabled_providers", _fake_load_providers
    )

    async def _refresh_one() -> None:
        async with sm() as session:
            await refresh_mod.refresh_game_metadata(
                session, game_id=game_id
            )

    await asyncio.gather(_refresh_one(), _refresh_one())

    # The lock serialises the two callers; the second one finds
    # the metadata_cache row populated by the first and skips
    # the provider fetch entirely.
    assert counting.search_calls == 1, (
        f"expected exactly 1 search_games call across two concurrent "
        f"refreshes, got {counting.search_calls}"
    )
    assert counting.get_game_calls == 1, (
        f"expected exactly 1 get_game call, got {counting.get_game_calls}"
    )


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache_per_call(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force=True`` skips the cache short-circuit on every call.

    The lock still serialises, so back-to-back forced refreshes
    each issue their own provider round (FR-013a's coalescing
    only kicks in when ``force=False``).
    """
    sm = async_sessionmaker_factory
    refresh_mod._GAME_LOCKS.clear()

    async with sm() as setup:
        platform = Platform(slug="megadrive", name="Mega Drive")
        setup.add(platform)
        await setup.flush()
        game = Game(
            platform_id=platform.id,
            slug="sonic-1",
            title="Sonic the Hedgehog",
        )
        setup.add(game)
        await setup.commit()
        game_id = game.id

    counting = _CountingProvider()

    async def _fake_load_providers(session: Any, scan: bool = True):
        return [counting]

    monkeypatch.setattr(
        refresh_mod, "load_enabled_providers", _fake_load_providers
    )

    async with sm() as session:
        await refresh_mod.refresh_game_metadata(
            session, game_id=game_id, force=True
        )
    async with sm() as session:
        await refresh_mod.refresh_game_metadata(
            session, game_id=game_id, force=True
        )

    assert counting.search_calls == 2
    assert counting.get_game_calls == 2
