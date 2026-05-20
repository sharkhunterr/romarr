"""Tests for ``refresh._search_title_variants`` (Advance Wars regression).

When the scan inserts ``Game.title='Advance Wars (USA)'`` (the No-Intro
filename minus extension), the metadata refresh used to call
``provider.search_games("Advance Wars (USA)")`` verbatim and got zero
hits — IGDB's ``name ~ *"…"*`` wildcard refuses to match anything that
contains the literal "(USA)". Result: the game ended up with only the
RetroAchievements cache (the one provider that binds by hash) and the
operator's library showed no IGDB / ScreenScraper / LaunchBox /
MobyGames metadata at all.

The helper now strips ``(…)`` / ``[…]`` tags + tries a subtitle-free
fallback so the same title hits a real provider entry.
"""

from __future__ import annotations

from romarr.metadata.refresh import _search_title_variants


def test_strips_region_parens() -> None:
    """The flagship case: "Advance Wars (USA)" → "Advance Wars" first."""
    variants = _search_title_variants("Advance Wars (USA)")
    assert variants[0] == "Advance Wars"
    # Raw form kept as a last-resort to preserve behaviour when the
    # caller already passed a clean title.
    assert "Advance Wars (USA)" in variants


def test_strips_multiple_paren_groups() -> None:
    variants = _search_title_variants(
        "Batman - Vengeance (Europe) (En,Fr,De,Es,It,Nl)"
    )
    # First variant is the stripped title with the subtitle still
    # present (the second separator strategy kicks in below if needed).
    assert variants[0] == "Batman - Vengeance"
    # Fallback drops the subtitle prefix after the " - " separator.
    assert "Batman" in variants


def test_strips_square_bracket_tags() -> None:
    """TOSEC-style ``[!]`` / ``[h]`` are dumped too."""
    variants = _search_title_variants("Sonic 3 [!] (USA)")
    assert variants[0] == "Sonic 3"


def test_subtitle_fallback_after_dash() -> None:
    """Provider stores ``Game 2: Subtitle`` not ``Game 2 - Subtitle``."""
    variants = _search_title_variants(
        "Advance Wars 2 - Black Hole Rising (USA)"
    )
    assert variants[0] == "Advance Wars 2 - Black Hole Rising"
    # Fallback drops the subtitle so a colon-form provider entry can hit.
    assert "Advance Wars 2" in variants


def test_clean_title_passes_through() -> None:
    """Titles without DAT tags get one variant — themselves."""
    variants = _search_title_variants("Metroid Fusion")
    assert variants == ["Metroid Fusion"]


def test_collapses_double_spaces_from_stripped_tags() -> None:
    """Stripping the middle ``(Beta)`` mustn't leave ``"Game  Title"``."""
    variants = _search_title_variants("Game Title (Beta) (USA)")
    assert variants[0] == "Game Title"


def test_empty_title_returns_empty() -> None:
    """Pathological input: only the parens / no actual name."""
    variants = _search_title_variants("(USA)")
    # The stripped form is empty; the raw form survives as the
    # last-resort variant.
    assert "(USA)" in variants


def test_no_duplicate_variants() -> None:
    """A title that's already clean shouldn't be emitted twice."""
    variants = _search_title_variants("Sonic")
    assert variants == ["Sonic"]


# ---------------------------------------------------------------------------
# _pick_best_candidate — second half of the Advance Wars fix.
# After widening the query we got hits, but ``candidates[0]`` from
# IGDB was "Advance Wars Returns" not "Advance Wars". Now we pick by
# confidence with a platform-match tiebreaker.

from types import SimpleNamespace as _NS  # noqa: E402

from romarr.metadata.refresh import _pick_best_candidate  # noqa: E402


def _c(title: str, confidence: float, platform: str | None = None) -> _NS:
    return _NS(
        provider_game_id=title,
        title=title,
        confidence=confidence,
        platform_slug=platform,
    )


def test_pick_best_returns_highest_confidence() -> None:
    """IGDB ships ``Advance Wars Returns`` first even though
    ``Advance Wars`` is a 1.0 exact match — we must pick the exact."""
    candidates = [
        _c("Advance Wars Returns", 0.5, "gba"),
        _c("Advance Wars", 1.0, "wiiu"),
        _c("Advance Wars", 1.0, "gba"),
    ]
    best = _pick_best_candidate(candidates, platform_slug="gba")
    # GBA wins the tiebreaker between two equal-confidence exact matches.
    assert best.platform_slug == "gba"
    assert best.title == "Advance Wars"


def test_pick_best_platform_tiebreaker_only_when_confidence_ties() -> None:
    """A higher-confidence wrong-platform hit still wins (we don't
    silently downgrade a 1.0 just because the platform mismatches)."""
    candidates = [
        _c("Advance Wars", 1.0, "wiiu"),
        _c("Advance Wars 2", 0.5, "gba"),
    ]
    best = _pick_best_candidate(candidates, platform_slug="gba")
    assert best.title == "Advance Wars"


def test_pick_best_without_platform_falls_back_to_confidence() -> None:
    candidates = [
        _c("X", 0.3),
        _c("Y", 0.9),
        _c("Z", 0.7),
    ]
    best = _pick_best_candidate(candidates, platform_slug=None)
    assert best.title == "Y"
