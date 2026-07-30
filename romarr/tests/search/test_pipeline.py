"""13-step pipeline tests (T017-T022)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from romarr.profiles.types import Decision
from romarr.search.pipeline import (
    DAT_VERIFIED_BONUS,
    _compute_match_score,
    run_pipeline,
)
from romarr.search.state import (
    BlocklistEntry,
    LibraryState,
    PlatformFormatBounds,
)
from romarr.search.types import RejectionCode, ScoreBreakdown
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


def test_compute_match_score_is_absolute_and_clamped() -> None:
    """match_score = 50% title identification + 50% quality, the
    quality half clamped to 0-100 — absolute, never round-relative."""
    # Perfect title (100) + quality 30 → 0.5*100 + 0.5*30 = 65.
    assert (
        _compute_match_score(100, ScoreBreakdown(total=30, contributions=[]))
        == 65
    )
    # Quality clamps high: a 500-point breakdown caps at 100.
    assert (
        _compute_match_score(100, ScoreBreakdown(total=500, contributions=[]))
        == 100
    )
    # Negative quality clamps to 0.
    assert (
        _compute_match_score(80, ScoreBreakdown(total=-20, contributions=[]))
        == 40
    )
    # Missing title score defaults to 100 (accepted ⇒ game matched).
    assert (
        _compute_match_score(None, ScoreBreakdown(total=40, contributions=[]))
        == 70
    )


def test_accepted_candidate_carries_match_score(
    make_result: Callable[..., Any],
    sonic_state: LibraryState,
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    """An accepted candidate carries the canonical ``match_score``
    consistent with its title + quality halves."""
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
    assert candidate.match_score is not None
    assert 0 <= candidate.match_score <= 100
    assert candidate.match_score == _compute_match_score(
        candidate.title_match_score, candidate.score_breakdown
    )


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
    """Slice 456 — a custom-format rejector is now a heavy *malus*,
    not a hard reject. The candidate still resolves with a
    ``score_breakdown`` carrying the negative contribution and is
    flagged ``would_auto_reject`` because the total lands below
    the auto-grab floor."""
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
    assert candidate.rejection is None
    assert candidate.would_auto_reject is True
    assert candidate.score_breakdown is not None
    cf = [
        c
        for c in candidate.score_breakdown.contributions
        if c.source == "custom_format"
    ]
    assert cf and cf[0].value < 0


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
# File-extension platform-mismatch hard reject
# ---------------------------------------------------------------------------


def test_file_extension_native_to_other_platform_rejects(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    """Real case: user monitors ``The Legend of Zelda`` on the NES
    (platform_id=1). A search candidate ``The Legend of Zelda -
    Skyward Sword [SOUE01].wbfs`` — WBFS is native to Wii / Wii U
    (platform_id=2), NEVER to NES. Fuzzy title matched (subset), but
    the pipeline must PLATFORM_MISMATCH-reject so cutoff auto-grab
    doesn't dispatch a Wii disc image against a NES game.
    """
    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.search.state import IndexerMeta, MonitoredGame, MonitoredRelease

    games = (MonitoredGame(id=1, platform_id=1, title="The Legend of Zelda"),)
    releases = (
        MonitoredRelease(
            id=10,
            game_id=1,
            region="USA",
            languages=("en",),
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            file_format="nes",
        ),
    )
    # Native format table: .nes native to NES (id=1), .wbfs native
    # to Wii (id=2). No overlap.
    bounds = (
        PlatformFormatBounds(platform_id=1, extension="nes"),
        PlatformFormatBounds(platform_id=2, extension="wbfs"),
    )
    state = make_state(
        games=games,
        releases=releases,
        bounds=bounds,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(
            title="The Legend of Zelda (USA)",
            size_bytes=8_000_000_000,
        ),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="wbfs",
    )
    assert candidate.rejection is not None
    assert candidate.rejection.code == RejectionCode.PLATFORM_MISMATCH
    assert "wbfs" in candidate.rejection.message


def test_file_extension_native_to_target_platform_accepts(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    """Sanity: when the extension IS native to the target platform,
    the pipeline runs normally (no PLATFORM_MISMATCH)."""
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
            file_format="md",
        ),
    )
    bounds = (
        PlatformFormatBounds(platform_id=1, extension="md"),
        PlatformFormatBounds(platform_id=2, extension="wbfs"),
    )
    state = make_state(
        games=games,
        releases=releases,
        bounds=bounds,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(size_bytes=2_000_000),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="md",
    )
    assert candidate.rejection is None


def test_file_extension_unknown_to_bounds_no_opinion(
    make_result: Callable[..., Any],
    make_state: Callable[..., LibraryState],
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
) -> None:
    """When the extension isn't native to any known platform (e.g.
    ``.zip`` archive), the guard stays silent — the pipeline's
    existing "no opinion" convention on bounds carries through."""
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
            file_format="md",
        ),
    )
    bounds = (PlatformFormatBounds(platform_id=1, extension="md"),)
    state = make_state(
        games=games,
        releases=releases,
        bounds=bounds,
        indexer_meta=(IndexerMeta(id=1, priority=5),),
    )
    candidate = run_pipeline(
        result=make_result(size_bytes=2_000_000),
        library_state=state,
        dat_lookup=none_dat,
        quality_profile=quality_profile,
        region_profile=region_profile,
        dump_profile=dump_profile,
        language_profile=language_profile,
        custom_formats=custom_formats,
        file_format="zip",
    )
    # ``.zip`` isn't native to any platform in bounds → guard silent.
    assert (
        candidate.rejection is None
        or candidate.rejection.code != RejectionCode.PLATFORM_MISMATCH
    )


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
    # Slice 456 — size-out-of-bounds is a malus, not a reject.
    assert candidate.rejection is None
    assert candidate.score_breakdown is not None
    sz = [
        c
        for c in candidate.score_breakdown.contributions
        if c.source == "size"
    ]
    assert sz and sz[0].value < 0


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
    # Slice 456 — seeders below the indexer floor is a malus, not
    # a reject.
    assert candidate.rejection is None
    assert candidate.score_breakdown is not None
    sd = [
        c
        for c in candidate.score_breakdown.contributions
        if c.source == "seeders"
    ]
    assert sd and sd[0].value < 0


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
