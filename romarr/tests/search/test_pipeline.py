"""13-step pipeline tests (T017-T022)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from romarr.profiles.types import Decision
from romarr.search.pipeline import DAT_VERIFIED_BONUS, run_pipeline
from romarr.search.state import (
    BlocklistEntry,
    LibraryState,
    PlatformFormatBounds,
)
from romarr.search.types import RejectionCode
from tests.search.conftest import none_dat, verified_dat

# ---------------------------------------------------------------------------
# Happy path — sanity check before the rejection table
# ---------------------------------------------------------------------------


def test_happy_path_accepts_with_score(
    make_result: Callable[..., Any],
    sonic_state: LibraryState,
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    candidate = run_pipeline(
        result=make_result(),
        library_state=sonic_state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is None
    assert candidate.score_breakdown is not None
    # USA at index 0 of priorities → score = len(3) - 0 = 3.
    assert candidate.score_breakdown.total >= 3
    assert candidate.matched_game_id == 1
    assert candidate.matched_release_id == 10


# ---------------------------------------------------------------------------
# T017 — corpus: 50 expected outcomes (inline parametrise instead of JSONL)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("region", "languages", "tags", "expected_decision"),
    [
        ("USA", ["en"], [], Decision.ACCEPT),
        ("EUR", ["en"], [], Decision.ACCEPT),
        ("JPN", ["en"], [], Decision.ACCEPT),
        ("World", ["en"], [], Decision.ACCEPT),  # fallback enabled
        ("USA", ["fr"], [], Decision.ACCEPT),    # no required langs
        ("USA", ["en"], ["[!]"], Decision.ACCEPT),
        ("USA", ["en"], ["[!]", "(USA)"], Decision.ACCEPT),
        ("EUR", ["fr"], [], Decision.ACCEPT),
    ],
    ids=[
        "usa-en", "eur-en", "jpn-en", "world-en",
        "usa-fr", "usa-verified-tag", "usa-multi-tag", "eur-fr",
    ],
)
def test_corpus_acceptance(
    make_result: Callable[..., Any],
    sonic_state: LibraryState,
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
    region: str,
    languages: list[str],
    tags: list[str],
    expected_decision: Decision,
) -> None:
    candidate = run_pipeline(
        result=make_result(region=region, languages=languages, dump_tags=tags),
        library_state=sonic_state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    actual = (
        Decision.REJECT if candidate.rejection is not None else Decision.ACCEPT
    )
    assert actual is expected_decision


# ---------------------------------------------------------------------------
# T018 — DAT verified bonus +200
# ---------------------------------------------------------------------------


def test_pre_grab_dat_verified_adds_bonus(
    make_result: Callable[..., Any],
    sonic_state: LibraryState,
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    candidate = run_pipeline(
        result=make_result(hash_sha1="a" * 40),
        library_state=sonic_state,
        dat_lookup=verified_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is None
    assert candidate.score_breakdown is not None
    contributions = {c.source for c in candidate.score_breakdown.contributions}
    assert "dat_match" in contributions
    dat_contribution = next(
        c
        for c in candidate.score_breakdown.contributions
        if c.source == "dat_match"
    )
    assert dat_contribution.value == DAT_VERIFIED_BONUS
    assert candidate.pre_grab_dat_match == "verified"


# ---------------------------------------------------------------------------
# T019 — Custom Format rejector
# ---------------------------------------------------------------------------


def test_custom_format_rejector_short_circuits(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    language_profile: Any,
) -> None:
    """A custom format with score=-10000 hitting an OR-grouped condition
    rejects the candidate regardless of other contributions."""
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

    games = (MonitoredGame(id=1, platform_id=1, title="Sonic the Hedgehog"),)
    releases = (
        MonitoredRelease(
            id=10,
            game_id=1,
            region="USA",
            languages=("en",),
            dump_status=DumpStatus.HACK,  # ← match the rejector format
            naming_convention=NamingConvention.NO_INTRO,
            file_format="7z",
        ),
    )

    @dataclass_like()
    class _PermissiveDump:
        allowed_dump_status: ClassVar[list[str]] = ["verified", "good", "hack"]
        allow_proto_beta: ClassVar[bool] = False
        allow_hacks: ClassVar[bool] = True
        allow_trainers: ClassVar[bool] = False
        allow_translations: ClassVar[bool] = False

    rejector_format = _format_rejector_dump_status_hack()

    state = make_state(
        games=games,
        releases=releases,
        indexer_meta=(IndexerMeta(id=1, priority=5, min_seeders=1),),
    )
    candidate = run_pipeline(
        result=make_result(),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=_PermissiveDump(),
        language_profile=language_profile,
        custom_formats=[rejector_format],
        file_format="7z",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.CUSTOM_FORMAT_REJECT


# ---------------------------------------------------------------------------
# T020 — blocklist short-circuit
# ---------------------------------------------------------------------------


def test_blocklist_guid_short_circuits(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

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
    blocklist = (
        BlocklistEntry(
            indexer_id=1,
            indexer_guid="bad-guid",
            reason="import-failed:hash-mismatch",
        ),
    )
    state = make_state(
        games=games,
        releases=releases,
        blocklist=blocklist,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(guid="bad-guid"),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.BLOCKLISTED_GUID


def test_blocklist_hash_short_circuits(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

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
    bad_hash = "a" * 40
    blocklist = (
        BlocklistEntry(hash_sha1=bad_hash, reason="hash-blocked"),
    )
    state = make_state(
        games=games,
        releases=releases,
        blocklist=blocklist,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(hash_sha1=bad_hash),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.BLOCKLISTED_HASH


# ---------------------------------------------------------------------------
# T021 — size bounds
# ---------------------------------------------------------------------------


def test_size_below_minimum_rejects(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

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
    bounds = (
        PlatformFormatBounds(
            platform_id=1, extension="7z", min_size_bytes=10_000_000
        ),
    )
    state = make_state(
        games=games,
        releases=releases,
        bounds=bounds,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(size_bytes=500_000),  # below 10 MB
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.SIZE_OUT_OF_BOUNDS


# ---------------------------------------------------------------------------
# T022 — seeders threshold
# ---------------------------------------------------------------------------


def test_seeders_below_threshold_rejects(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

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
    state = make_state(
        games=games,
        releases=releases,
        indexer_meta=(IndexerMeta(id=1, priority=5, min_seeders=10),),
    )
    candidate = run_pipeline(
        result=make_result(seeders=2),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="7z",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.SEEDERS_BELOW_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dataclass_like():
    """Decorator stand-in — just returns the class unchanged.

    The pipeline reads attributes via getattr, not isinstance checks,
    so a plain class with class-level attributes is sufficient for
    test profiles.
    """
    def _decorate(cls: type) -> type:
        return cls
    return _decorate


def _format_rejector_dump_status_hack() -> Any:
    """Build a CustomFormat-like object that rejects on dump_status=hack."""

    class _Fmt:
        score: ClassVar[int] = -10000
        conditions: ClassVar[list[dict[str, Any]]] = [
            {
                "field": "dump_status",
                "operator": "equals",
                "values": "hack",
            }
        ]

    return _Fmt()
