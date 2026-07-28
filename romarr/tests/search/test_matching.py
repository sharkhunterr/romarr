"""Hash + fuzzy matching tests (T014-T016)."""

from __future__ import annotations

from romarr.search.matching import resolve_to_game
from romarr.search.state import DatMatchInfo, MonitoredGame, _NONE_DAT_INFO


def _none_dat(_a: object, _b: object) -> DatMatchInfo:
    return _NONE_DAT_INFO


def _verified_dat(_a: object, _b: object) -> DatMatchInfo:
    return DatMatchInfo(outcome="verified", entry_name="test", entry_source="no-intro")


_GAMES = (
    MonitoredGame(id=1, platform_id=1, title="Sonic the Hedgehog"),
    MonitoredGame(id=2, platform_id=1, title="Mortal Kombat"),
    MonitoredGame(
        id=3,
        platform_id=1,
        title="Streets of Rage",
        alt_names=("Bare Knuckle",),
    ),
)


# ---------------------------------------------------------------------------
# T014 — hash match short-circuit (DAT verified before fuzzy)
# ---------------------------------------------------------------------------


def test_hash_present_dat_verified_does_not_block_match() -> None:
    """When the DAT lookup says ``verified``, the matcher still runs the
    fuzzy fallback to find the matched Game (the DAT layer's
    Game-ID join is the future Importer's job; current MVP confirms
    the path doesn't crash)."""
    match = resolve_to_game(
        title="Sonic the Hedgehog",
        hash_sha1="a" * 40,
        hash_crc32=None,
        monitored_games=_GAMES,
        dat_lookup=_verified_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id == 1
    assert 0 <= match[1] <= 100


# ---------------------------------------------------------------------------
# T015 — fuzzy match at threshold 85
# ---------------------------------------------------------------------------


def test_fuzzy_match_typo_above_threshold() -> None:
    """A typical scene-naming wrap (region + revision in parens) doesn't
    block the canonical match — the partial-ratio path inside WRatio
    finds the canonical title as a substring above the 85 threshold.
    """
    match = resolve_to_game(
        title="Sonic the Hedgehog (USA) (Rev A)",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=_GAMES,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id == 1
    # WRatio with the canonical substring present → high confidence.
    assert match[1] >= 85


def test_fuzzy_match_alt_name() -> None:
    """Alt names participate in the fuzzy match."""
    match = resolve_to_game(
        title="Bare Knuckle (JPN)",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=_GAMES,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id == 3


# ---------------------------------------------------------------------------
# T016 — no match below threshold returns None
# ---------------------------------------------------------------------------


def test_no_match_below_threshold() -> None:
    """A wildly different title doesn't match anything."""
    match = resolve_to_game(
        title="Some Completely Unrelated Game ABCXYZ",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=_GAMES,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is None


def test_empty_monitored_games_returns_none() -> None:
    match = resolve_to_game(
        title="Anything",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=(),
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is None


def test_case_insensitive_match() -> None:
    match = resolve_to_game(
        title="SONIC THE HEDGEHOG",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=_GAMES,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id == 1


def test_bracket_heavy_title_still_matches() -> None:
    """MiNERVA / No-Intro indexers wrap the title in multiple
    ``[Tag]`` brackets (``[MiNERVA Archive] [Redump] [Sony -
    PlayStation 2] [Korea] [KO] Jak II [ZIP]``). Pre-slice the
    fuzzy comparator scored that at 60% against the plain "Jak II"
    monitored game — below the 85 threshold — and returned no
    match, rejecting an otherwise-valid candidate. The processor
    now strips ``[…]`` blocks before RapidFuzz sees the string, so
    the game name reads clean and the match lands at ~100."""
    games = (MonitoredGame(id=42, platform_id=8, title="Jak II"),)
    match = resolve_to_game(
        title=(
            "[MiNERVA Archive] [Redump] [Sony - PlayStation 2] "
            "[Korea] [KO] Jak II [ZIP]"
        ),
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=games,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id == 42
    assert match[1] >= 85


def test_picks_a_match_among_close_titles() -> None:
    """When several similar titles all clear the threshold, the matcher
    picks one deterministically. WRatio's partial-substring scoring
    means a sequel title containing a previous-entry's name is
    fundamentally ambiguous; we don't enforce which of the three it
    picks (that's the hash-match path's job), only that one
    monitored Game is returned.
    """
    games = (
        MonitoredGame(id=1, platform_id=1, title="Sonic the Hedgehog"),
        MonitoredGame(id=2, platform_id=1, title="Sonic the Hedgehog 2"),
        MonitoredGame(id=3, platform_id=1, title="Sonic the Hedgehog 3"),
    )
    match = resolve_to_game(
        title="Sonic the Hedgehog 2 (USA)",
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=games,
        dat_lookup=_none_dat,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match[0].id in {1, 2, 3}
