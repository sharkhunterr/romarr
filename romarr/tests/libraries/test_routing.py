"""Pure-function library router tests (T017-T023)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.libraries.routing import route_to_library
from romarr.libraries.types import LibrarySnapshot, LibraryStatus
from romarr.profiles.types import ReleaseFacts


@dataclass(frozen=True)
class _QualityProfile:
    """Duck-typed match for :class:`ProfileEvaluator._QualityShape`."""

    allowed_formats: list[str] = field(
        default_factory=lambda: ["raw", "zip", "7z", "chd", "iso"]
    )
    preferred_format: str = "7z"
    require_dat_verified: bool = False
    upgrade_until_format: str = "7z"


@dataclass(frozen=True)
class _RegionProfile:
    priorities: list[str] = field(default_factory=lambda: ["USA", "EUR"])
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


def _snapshot(
    *,
    library_id: int,
    status: LibraryStatus = LibraryStatus.OK,
    platforms_restricted: bool = False,
    accepted_platform_ids: frozenset[int] = frozenset(),
    quality_profile_id: int = 1,
    region_profile_id: int = 1,
) -> LibrarySnapshot:
    return LibrarySnapshot(
        id=library_id,
        name=f"library-{library_id}",
        path=Path(f"/var/lib/romarr/{library_id}"),
        status=status,
        platforms_restricted=platforms_restricted,
        accepted_platform_ids=accepted_platform_ids,
        quality_profile_id=quality_profile_id,
        region_profile_id=region_profile_id,
        dump_profile_id=1,
        language_profile_id=1,
        naming_profile_id=1,
        use_hardlinks=True,
        lifecycle_policy="hardlink_and_seed",
        keep_dump_history=False,
        min_disk_free_gb=5,
        preserve_archive=False,
    )


def _facts(
    *,
    region: str = "USA",
    file_format: str = "7z",
) -> ReleaseFacts:
    return ReleaseFacts(
        title="Sonic the Hedgehog",
        regions=(region,),
        languages=("en",),
        revision=None,
        dump_status=DumpStatus.VERIFIED,
        tags=(),
        naming_convention=NamingConvention.NO_INTRO,
        file_format=file_format,
        dat_verified=True,
        indexer_source="filesystem",
        release_size=1_000_000,
        release_group=None,
    )


def _default_profile_maps() -> tuple[
    Mapping[int, _QualityProfile], Mapping[int, _RegionProfile]
]:
    return {1: _QualityProfile()}, {1: _RegionProfile()}


# ---------------------------------------------------------------------------
# T017 — only one library accepts the platform
# ---------------------------------------------------------------------------


def test_only_eligible_wins() -> None:
    libs = (
        _snapshot(library_id=1, platforms_restricted=True, accepted_platform_ids=frozenset({100})),
        _snapshot(library_id=2, platforms_restricted=True, accepted_platform_ids=frozenset({101})),
        _snapshot(library_id=3, platforms_restricted=True, accepted_platform_ids=frozenset({102})),
    )
    quality_map, region_map = _default_profile_maps()

    choice = route_to_library(
        facts=_facts(),
        inferred_platform_id=101,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id == 2
    assert choice.chosen_via == "only_eligible"


# ---------------------------------------------------------------------------
# T018 — unrestricted library accepts all platforms
# ---------------------------------------------------------------------------


def test_unrestricted_library_accepts_all() -> None:
    libs = (_snapshot(library_id=1, platforms_restricted=False),)
    quality_map, region_map = _default_profile_maps()

    choice = route_to_library(
        facts=_facts(),
        inferred_platform_id=42,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id == 1


# ---------------------------------------------------------------------------
# T019 — profile match breaks the tie
# ---------------------------------------------------------------------------


def test_profile_match_breaks_tie() -> None:
    libs = (
        _snapshot(library_id=1, region_profile_id=10),  # priorities=["USA","EUR"], USA→score 2
        _snapshot(library_id=2, region_profile_id=20),  # priorities=["EUR","USA"], USA→score 1
    )
    quality_map: Mapping[int, _QualityProfile] = {1: _QualityProfile()}
    region_map: Mapping[int, _RegionProfile] = {
        10: _RegionProfile(priorities=["USA", "EUR"]),
        20: _RegionProfile(priorities=["EUR", "USA"]),
    }

    choice = route_to_library(
        facts=_facts(region="USA"),
        inferred_platform_id=100,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    # Library 1 scores 2 (region) + 1 (quality accept) = 3
    # Library 2 scores 1 (region) + 1 (quality accept) = 2
    assert choice.chosen_library_id == 1
    assert choice.chosen_via == "profile_match"


# ---------------------------------------------------------------------------
# T020 — final tiebreak goes to lower id
# ---------------------------------------------------------------------------


def test_lower_id_final_tiebreak() -> None:
    libs = (
        _snapshot(library_id=2),
        _snapshot(library_id=1),
        _snapshot(library_id=3),
    )
    quality_map, region_map = _default_profile_maps()

    choice = route_to_library(
        facts=_facts(),
        inferred_platform_id=100,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id == 1
    assert choice.chosen_via == "lower_id_tiebreak"


# ---------------------------------------------------------------------------
# T021 — unavailable library is skipped
# ---------------------------------------------------------------------------


def test_unavailable_skipped() -> None:
    libs = (
        _snapshot(library_id=1, status=LibraryStatus.UNAVAILABLE),
        _snapshot(library_id=2),
    )
    quality_map, region_map = _default_profile_maps()

    choice = route_to_library(
        facts=_facts(),
        inferred_platform_id=100,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id == 2
    assert choice.candidates_considered == (2,)


# ---------------------------------------------------------------------------
# T022 — no eligible library
# ---------------------------------------------------------------------------


def test_no_eligible_library() -> None:
    libs = (
        _snapshot(
            library_id=1, platforms_restricted=True, accepted_platform_ids=frozenset({100})
        ),
        _snapshot(
            library_id=2, platforms_restricted=True, accepted_platform_ids=frozenset({101})
        ),
    )
    quality_map, region_map = _default_profile_maps()

    choice = route_to_library(
        facts=_facts(),
        inferred_platform_id=999,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id is None
    assert choice.chosen_via == "no_eligible_library"
    assert choice.rejection_reason == "routing:no_library_for_platform"


def test_region_excluded_disqualifies_library() -> None:
    """If the only eligible library's Region profile excludes the
    release's region outright, the router falls through to
    no_eligible_library (FR-006)."""
    libs = (_snapshot(library_id=1, region_profile_id=10),)
    quality_map: Mapping[int, _QualityProfile] = {1: _QualityProfile()}
    region_map: Mapping[int, _RegionProfile] = {
        10: _RegionProfile(priorities=["EUR"], exclude_regions=["JPN"])
    }

    choice = route_to_library(
        facts=_facts(region="JPN"),
        inferred_platform_id=100,
        libraries=libs,
        quality_profiles=quality_map,
        region_profiles=region_map,
    )
    assert choice.chosen_library_id is None
    assert choice.chosen_via == "no_eligible_library"


# ---------------------------------------------------------------------------
# T023 — 30-release corpus (SC-002)
# ---------------------------------------------------------------------------


def test_30_release_corpus_routes_deterministically() -> None:
    """Mini-corpus stress test: 30 USA-region releases all route to
    the USA-priority library and never flap. We don't carry a 30-line
    JSONL fixture into the repo for this; we synthesise the corpus
    inline so the test stays self-contained and fast."""
    libs = (
        _snapshot(library_id=1, region_profile_id=10),  # USA-priority
        _snapshot(library_id=2, region_profile_id=20),  # EUR-priority
        _snapshot(library_id=3, region_profile_id=30),  # JPN-priority
    )
    quality_map: Mapping[int, _QualityProfile] = {1: _QualityProfile()}
    region_map: Mapping[int, _RegionProfile] = {
        10: _RegionProfile(priorities=["USA", "EUR", "JPN"]),
        20: _RegionProfile(priorities=["EUR", "USA", "JPN"]),
        30: _RegionProfile(priorities=["JPN", "USA", "EUR"]),
    }

    # Every USA release routes to library 1 deterministically.
    for i in range(30):
        choice = route_to_library(
            facts=_facts(region="USA"),
            inferred_platform_id=100 + (i % 5),
            libraries=libs,
            quality_profiles=quality_map,
            region_profiles=region_map,
        )
        assert choice.chosen_library_id == 1, f"corpus run {i} flapped"

    # JPN releases consistently route to library 3.
    for i in range(10):
        choice = route_to_library(
            facts=_facts(region="JPN"),
            inferred_platform_id=200 + i,
            libraries=libs,
            quality_profiles=quality_map,
            region_profiles=region_map,
        )
        assert choice.chosen_library_id == 3
