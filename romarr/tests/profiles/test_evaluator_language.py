"""Language evaluator tests (T025-T026)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.types import Decision, ReleaseFacts


@dataclass
class _LanguageProfile:
    required_languages: list[str] = field(default_factory=list)
    preferred_languages: list[str] = field(default_factory=list)
    exclude_japanese_only: bool = True


# ---------------------------------------------------------------------------
# T025 — required_languages is any-of
# ---------------------------------------------------------------------------


def test_any_of_match_accepts(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _LanguageProfile(required_languages=["fr", "en"])
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("en", "de"))
    )
    assert result.decision is Decision.ACCEPT


def test_no_required_match_rejects(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _LanguageProfile(required_languages=["fr", "en"])
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("de",))
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "required_language_missing"


def test_empty_required_accepts_anything(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _LanguageProfile(required_languages=[])
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("xx",))
    )
    assert result.decision is Decision.ACCEPT


# ---------------------------------------------------------------------------
# T026 — Japanese-only exclusion
# ---------------------------------------------------------------------------


def test_japanese_only_rejected(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _LanguageProfile(exclude_japanese_only=True)
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("ja",))
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "japanese_only_excluded"


def test_japanese_plus_other_not_rejected(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """Japanese release with another language is fine."""
    profile = _LanguageProfile(exclude_japanese_only=True)
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("ja", "en"))
    )
    assert result.decision is Decision.ACCEPT


def test_japanese_only_allowed_when_flag_off(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    profile = _LanguageProfile(exclude_japanese_only=False)
    result = ProfileEvaluator.evaluate_language(
        profile, make_facts(languages=("ja",))
    )
    assert result.decision is Decision.ACCEPT
