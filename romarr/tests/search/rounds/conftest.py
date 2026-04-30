"""Shared fixtures for the round-orchestrator tests.

Builds a mocked NewznabClient factory that yields lab-controlled
results without going through respx — the orchestrator passes the
factory in, so we don't need to monkey-patch anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.indexers.models import Indexer
from romarr.indexers.types import SearchResult
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


class _FakeNewznabClient:
    """Stub that mimics :class:`NewznabClient` for orchestrator tests.

    Implements only the surface the rounds use: ``search`` (manual),
    ``rss`` (rss-sync), and ``aclose``. Every method is async + free
    of network I/O.
    """

    def __init__(
        self,
        *,
        indexer_id: int,
        search_results: list[SearchResult] | None = None,
        rss_results: list[SearchResult] | None = None,
        raise_on_search: BaseException | None = None,
    ) -> None:
        self.indexer_id = indexer_id
        self._search_results = search_results or []
        self._rss_results = rss_results or []
        self._raise_on_search = raise_on_search
        self.search_calls: list[str] = []
        self.rss_calls: int = 0
        self.closed = False

    async def search(
        self, query: str, *, categories: Any = None
    ) -> list[SearchResult]:
        del categories
        self.search_calls.append(query)
        if self._raise_on_search is not None:
            raise self._raise_on_search
        return list(self._search_results)

    async def rss(self, *, categories: Any = None) -> list[SearchResult]:
        del categories
        self.rss_calls += 1
        return list(self._rss_results)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_client_factory() -> (
    Callable[[dict[int, _FakeNewznabClient]], Callable[[int], Awaitable[_FakeNewznabClient]]]
):
    """Build an async factory that resolves indexer_id → fake client."""

    def _make_factory(
        clients: dict[int, _FakeNewznabClient],
    ) -> Callable[[int], Awaitable[_FakeNewznabClient]]:
        async def _factory(indexer_id: int) -> _FakeNewznabClient:
            return clients[indexer_id]

        return _factory

    return _make_factory


# ---------------------------------------------------------------------------
# DB seeders — every round test needs at least one indexer + a profile set.
# ---------------------------------------------------------------------------


async def seed_minimal_world(
    session: AsyncSession,
    *,
    indexer_count: int = 1,
    rss_auto_grab: bool = True,
    enable_rss: bool = True,
) -> tuple[list[Indexer], Platform, Game]:
    """Seed: one Platform + one Game + one Release + N indexers + one
    profile per type. Returns the indexers list, platform, and game.
    """
    platform = Platform(slug="megadrive", name="Mega Drive")
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-the-hedgehog",
        title="Sonic the Hedgehog",
        sort_title="Sonic the Hedgehog",
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["USA"],
        languages=["en"],
        revision=None,
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        monitored=True,
    )
    session.add(release)

    indexers: list[Indexer] = []
    for i in range(indexer_count):
        idx = Indexer(
            name=f"Indexer {i}",
            implementation="newznab",
            url=f"https://idx-{i}.test/api",
            categories=[1060],
            source="manual",
            enable_rss=enable_rss,
            rss_auto_grab=rss_auto_grab,
        )
        session.add(idx)
        indexers.append(idx)

    # Profile set — seed one factory-default per type.
    session.add(
        QualityProfile(
            name="Q",
            allowed_formats=["raw", "zip", "7z"],
            preferred_format="7z",
            require_dat_verified=False,
            upgrade_until_format="7z",
            is_factory_default=True,
            seed_key="q",
        )
    )
    session.add(
        RegionProfile(
            name="R",
            priorities=["USA", "EUR"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
            is_factory_default=True,
            seed_key="r",
        )
    )
    session.add(
        DumpProfile(
            name="D",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
            prefer_revision="latest",
            is_factory_default=True,
            seed_key="d",
        )
    )
    session.add(
        LanguageProfile(
            name="L",
            required_languages=[],
            preferred_languages=[],
            exclude_japanese_only=False,
            is_factory_default=True,
            seed_key="l",
        )
    )
    session.add(
        NamingProfile(
            name="N",
            convention="no-intro",
            template="{{ Game.Title }}.{{ Dump.Extension }}",
            platform_subfolder=True,
            replace_illegal_chars=True,
            multi_disc_subfolder=True,
            is_factory_default=True,
            seed_key="n",
        )
    )
    await session.commit()
    for idx in indexers:
        await session.refresh(idx)
    return indexers, platform, game


def make_search_result(
    *,
    indexer_id: int,
    guid: str = "g1",
    title: str = "Sonic the Hedgehog (USA)",
    region: str | None = "USA",
    languages: list[str] | None = None,
    dump_tags: list[str] | None = None,
) -> SearchResult:
    return SearchResult(
        indexer_id=indexer_id,
        guid=guid,
        title=title,
        link=f"https://idx-{indexer_id}.test/{guid}",
        size_bytes=1_000_000,
        seeders=10,
        region=region,
        languages=languages or ["en"],
        dump_tags=dump_tags or [],
        naming_convention=NamingConvention.NO_INTRO,
    )
