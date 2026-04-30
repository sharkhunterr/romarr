"""Pipeline performance test (T024 / SC-003).

Score 100 results post-network in < 200 ms. Realistic budget for the
search-mode round handler — the network round-trip dominates total
time, but the in-memory pipeline must not eat into it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.indexers.types import SearchResult
from romarr.search.pipeline import run_pipeline
from romarr.search.state import (
    IndexerMeta,
    LibraryState,
    MonitoredGame,
    MonitoredRelease,
)


def _none_dat(_a: object, _b: object) -> str:
    return "none"


@dataclass
class _Q:
    allowed_formats: list[str] = field(default_factory=lambda: ["7z"])
    preferred_format: str = "7z"
    require_dat_verified: bool = False
    upgrade_until_format: str = "7z"


@dataclass
class _R:
    priorities: list[str] = field(default_factory=lambda: ["USA"])
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


@dataclass
class _D:
    allowed_dump_status: list[str] = field(default_factory=lambda: ["verified"])
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False


@dataclass
class _L:
    required_languages: list[str] = field(default_factory=list)
    preferred_languages: list[str] = field(default_factory=list)
    exclude_japanese_only: bool = False


def test_100_results_under_200_ms() -> None:
    state = LibraryState(
        monitored_games=(
            MonitoredGame(id=1, platform_id=1, title="Sonic the Hedgehog"),
        ),
        monitored_releases=(
            MonitoredRelease(
                id=10,
                game_id=1,
                region="USA",
                languages=("en",),
                dump_status=DumpStatus.VERIFIED,
                naming_convention=NamingConvention.NO_INTRO,
                file_format="7z",
            ),
        ),
        indexer_meta=(IndexerMeta(id=1, priority=5, min_seeders=1),),
    )
    quality = _Q()
    region = _R()
    dump = _D()
    language = _L()

    results = [
        SearchResult(
            indexer_id=1,
            guid=f"guid-{i}",
            title="Sonic the Hedgehog (USA)",
            link=f"https://idx.test/{i}",
            size_bytes=1_000_000 + i * 1000,
            seeders=10,
            region="USA",
            languages=["en"],
            naming_convention=NamingConvention.NO_INTRO,
        )
        for i in range(100)
    ]

    start = time.perf_counter()
    for result in results:
        run_pipeline(
            result=result,
            library_state=state,
            dat_lookup=_none_dat,  # type: ignore[arg-type]
            quality_profile=quality,
            region_profile=region,
            dump_profile=dump,
            language_profile=language,
            custom_formats=[],
            file_format="7z",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 200, f"100-result pipeline took {elapsed_ms:.1f} ms (budget 200 ms)"
