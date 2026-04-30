"""Module-local fixtures for search tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.indexers.types import SearchResult
from romarr.search.state import (
    BlocklistEntry,
    IndexerMeta,
    LibraryState,
    MonitoredGame,
    MonitoredRelease,
    PlatformFormatBounds,
)


@dataclass
class _Quality:
    allowed_formats: list[str] = field(
        default_factory=lambda: ["raw", "zip", "7z"]
    )
    preferred_format: str = "7z"
    require_dat_verified: bool = False
    upgrade_until_format: str = "7z"


@dataclass
class _Region:
    priorities: list[str] = field(default_factory=lambda: ["USA", "EUR", "JPN"])
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


@dataclass
class _Dump:
    allowed_dump_status: list[str] = field(
        default_factory=lambda: ["verified", "good"]
    )
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False


@dataclass
class _Language:
    required_languages: list[str] = field(default_factory=list)
    preferred_languages: list[str] = field(default_factory=list)
    exclude_japanese_only: bool = False


@dataclass
class _Format:
    score: int
    conditions: list[dict[str, Any]]


@pytest.fixture
def quality_profile() -> _Quality:
    return _Quality()


@pytest.fixture
def region_profile() -> _Region:
    return _Region()


@pytest.fixture
def dump_profile() -> _Dump:
    return _Dump()


@pytest.fixture
def language_profile() -> _Language:
    return _Language()


@pytest.fixture
def custom_formats() -> list[_Format]:
    return [
        _Format(
            score=100,
            conditions=[
                {"field": "tags", "operator": "matches_regex", "values": r"\[!\]"}
            ],
        ),
        _Format(
            score=-10000,
            conditions=[
                {
                    "field": "dump_status",
                    "operator": "equals",
                    "values": "hack",
                }
            ],
        ),
    ]


@pytest.fixture
def make_state() -> Callable[..., LibraryState]:
    def _build(
        *,
        games: tuple[MonitoredGame, ...] = (),
        releases: tuple[MonitoredRelease, ...] = (),
        bounds: tuple[PlatformFormatBounds, ...] = (),
        blocklist: tuple[BlocklistEntry, ...] = (),
        indexer_meta: tuple[IndexerMeta, ...] = (),
    ) -> LibraryState:
        return LibraryState(
            monitored_games=games,
            monitored_releases=releases,
            platform_format_bounds=bounds,
            blocklist=blocklist,
            indexer_meta=indexer_meta,
        )

    return _build


@pytest.fixture
def make_result() -> Callable[..., SearchResult]:
    def _build(
        *,
        title: str = "Sonic the Hedgehog (USA)",
        guid: str = "guid-1",
        indexer_id: int = 1,
        link: str = "https://idx.test/file.torrent",
        size_bytes: int | None = 1_000_000,
        seeders: int | None = 10,
        region: str | None = "USA",
        languages: list[str] | None = None,
        revision: str | None = None,
        hash_sha1: str | None = None,
        hash_crc32: str | None = None,
        dump_tags: list[str] | None = None,
        naming_convention: NamingConvention | None = None,
    ) -> SearchResult:
        return SearchResult(
            indexer_id=indexer_id,
            guid=guid,
            title=title,
            link=link,
            size_bytes=size_bytes,
            seeders=seeders,
            region=region,
            languages=languages or ["en"],
            revision=revision,
            hash_sha1=hash_sha1,
            hash_crc32=hash_crc32,
            dump_tags=dump_tags or [],
            naming_convention=naming_convention or NamingConvention.NO_INTRO,
        )

    return _build


@pytest.fixture
def sonic_state(make_state: Callable[..., LibraryState]) -> LibraryState:
    """Library with Sonic the Hedgehog monitored on platform 1."""
    games = (MonitoredGame(id=1, platform_id=1, title="Sonic the Hedgehog"),)
    releases = (
        MonitoredRelease(
            id=10,
            game_id=1,
            region="USA",
            languages=("en",),
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            file_format="7z",
        ),
    )
    indexer_meta = (IndexerMeta(id=1, priority=5, min_seeders=1),)
    return make_state(games=games, releases=releases, indexer_meta=indexer_meta)


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


def none_dat(_a: object, _b: object) -> str:
    """Default DAT lookup returning ``"none"`` — no DAT match."""
    return "none"


def verified_dat(_a: object, _b: object) -> str:
    """DAT lookup returning ``"verified"`` — bonus +200."""
    return "verified"
