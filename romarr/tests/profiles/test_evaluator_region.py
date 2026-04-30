"""Region evaluator tests (T020-T022)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.types import Decision, ReleaseFacts


@dataclass
class _RegionProfile:
    priorities: list[str] = field(default_factory=list)
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# T020 — priority score = len(priorities) - index
# ---------------------------------------------------------------------------


def test_priority_score_first_priority_top_score(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _RegionProfile(priorities=["USA", "EUR", "World", "JPN"])
    result = ProfileEvaluator.evaluate_region(profile, make_facts(regions=("USA",)))
    assert result.decision is Decision.ACCEPT
    assert result.score == 4  # len(4) - index(0) = 4


def test_priority_score_lower_priority_smaller_score(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _RegionProfile(priorities=["USA", "EUR", "World", "JPN"])
    result = ProfileEvaluator.evaluate_region(profile, make_facts(regions=("JPN",)))
    assert result.score == 1  # len(4) - index(3) = 1


def test_multi_region_picks_best_score(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _RegionProfile(priorities=["USA", "EUR"])
    result = ProfileEvaluator.evaluate_region(
        profile, make_facts(regions=("EUR", "USA"))
    )
    assert result.score == 2  # USA at index 0 wins


# ---------------------------------------------------------------------------
# T021 — excluded region rejected outright
# ---------------------------------------------------------------------------


def test_excluded_region_rejects(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _RegionProfile(
        priorities=["USA", "EUR"], exclude_regions=["KOR"]
    )
    result = ProfileEvaluator.evaluate_region(
        profile, make_facts(regions=("KOR",))
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "region_excluded"


def test_excluded_region_in_multi_release_rejects(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """Even a partial exclusion (one region in the multi-region list) rejects."""
    profile = _RegionProfile(
        priorities=["USA"], exclude_regions=["KOR"]
    )
    result = ProfileEvaluator.evaluate_region(
        profile, make_facts(regions=("USA", "KOR"))
    )
    assert result.decision is Decision.REJECT


# ---------------------------------------------------------------------------
# T022 — fallback path
# ---------------------------------------------------------------------------


def test_fallback_accepts_outside_priorities(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _RegionProfile(
        priorities=["USA"], allow_fallback_outside_priorities=True
    )
    result = ProfileEvaluator.evaluate_region(
        profile, make_facts(regions=("EUR",))
    )
    assert result.decision is Decision.ACCEPT
    assert result.score == 0  # fallback


def test_no_fallback_rejects_outside_priorities(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _RegionProfile(
        priorities=["USA"], allow_fallback_outside_priorities=False
    )
    result = ProfileEvaluator.evaluate_region(
        profile, make_facts(regions=("EUR",))
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "region_not_in_priorities"
