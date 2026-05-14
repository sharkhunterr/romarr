"""Pipeline purity property test (T023 / FR-016 / SC-001).

Hypothesis-driven: 250+ randomized inputs; calling the pipeline
twice in a row MUST return identical Candidate objects (same
decision, same total score, same rejection if any). The pipeline
is pure by design — this test enforces the invariant against
future regressions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hypothesis import given, settings
from hypothesis import strategies as st

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.indexers.types import SearchResult
from romarr.search.pipeline import run_pipeline
from romarr.search.state import (
    BlocklistEntry,
    IndexerMeta,
    LibraryState,
    MonitoredGame,
    MonitoredRelease,
)


from romarr.search.state import DatMatchInfo, _NONE_DAT_INFO


def _none_dat(_a: object, _b: object):  # noqa: ANN202
    return _NONE_DAT_INFO


def _verified_dat(_a: object, _b: object):  # noqa: ANN202
    return DatMatchInfo(
        outcome="verified", entry_name="test", entry_source="no-intro"
    )


@dataclass
class _Q:
    allowed_formats: list[str] = field(
        default_factory=lambda: ["raw", "zip", "7z", "chd"]
    )
    preferred_format: str = "7z"
    require_dat_verified: bool = False
    upgrade_until_format: str = "7z"


@dataclass
class _R:
    priorities: list[str] = field(default_factory=lambda: ["USA", "EUR"])
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


_LIBRARY_STATE = LibraryState(
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
    blocklist=(BlocklistEntry(hash_sha1="b" * 40, reason="known-bad"),),
    indexer_meta=(IndexerMeta(id=1, priority=5, min_seeders=1),),
)


_result_strategy = st.builds(
    SearchResult,
    indexer_id=st.just(1),
    guid=st.text(min_size=1, max_size=12),
    title=st.sampled_from(
        [
            "Sonic the Hedgehog (USA)",
            "Sonic the Hedgehog (EUR)",
            "Sonic the Hedgehog (JPN)",
            "Mortal Kombat (USA)",  # no game match
        ]
    ),
    link=st.just("https://idx.test/file"),
    size_bytes=st.one_of(st.none(), st.integers(min_value=1, max_value=10**10)),
    seeders=st.one_of(st.none(), st.integers(min_value=0, max_value=200)),
    region=st.sampled_from(["USA", "EUR", "JPN", None]),
    languages=st.lists(
        st.sampled_from(["en", "fr", "ja", "de"]),
        min_size=0,
        max_size=2,
    ),
    revision=st.one_of(st.none(), st.sampled_from(["", "Rev A", "Rev B"])),
    dump_tags=st.lists(
        st.sampled_from(["[!]", "[h]", "[t]"]),
        min_size=0,
        max_size=2,
    ),
    naming_convention=st.sampled_from(list(NamingConvention)),
    hash_sha1=st.one_of(st.none(), st.just("a" * 40), st.just("b" * 40)),
)


@given(result=_result_strategy)
@settings(max_examples=250, deadline=None)
def test_pipeline_is_pure(result: SearchResult) -> None:
    quality = _Q()
    region = _R()
    dump = _D()
    language = _L()

    first = run_pipeline(
        result=result,
        library_state=_LIBRARY_STATE,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
        quality_profile=quality,
        region_profile=region,
        dump_profile=dump,
        language_profile=language,
        custom_formats=[],
        file_format="7z",
    )
    second = run_pipeline(
        result=result,
        library_state=_LIBRARY_STATE,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
        quality_profile=quality,
        region_profile=region,
        dump_profile=dump,
        language_profile=language,
        custom_formats=[],
        file_format="7z",
    )
    assert first == second


@given(result=_result_strategy)
@settings(max_examples=100, deadline=None)
def test_pipeline_purity_with_verified_dat_lookup(
    result: SearchResult,
) -> None:
    """Same property under a different DAT outcome — covers the bonus path."""
    first = run_pipeline(
        result=result,
        library_state=_LIBRARY_STATE,
        dat_lookup=_verified_dat,  # type: ignore[arg-type]
        quality_profile=_Q(),
        region_profile=_R(),
        dump_profile=_D(),
        language_profile=_L(),
        custom_formats=[],
        file_format="7z",
    )
    second = run_pipeline(
        result=result,
        library_state=_LIBRARY_STATE,
        dat_lookup=_verified_dat,  # type: ignore[arg-type]
        quality_profile=_Q(),
        region_profile=_R(),
        dump_profile=_D(),
        language_profile=_L(),
        custom_formats=[],
        file_format="7z",
    )
    assert first == second
