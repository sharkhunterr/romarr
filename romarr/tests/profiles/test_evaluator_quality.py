"""Quality evaluator tests (T017-T019)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.types import Decision, ReleaseFacts


@dataclass
class _QualityProfile:
    allowed_formats: list[str]
    preferred_format: str
    require_dat_verified: bool
    upgrade_until_format: str


def _profile(**overrides: object) -> _QualityProfile:
    base: dict[str, object] = {
        "allowed_formats": ["raw", "zip", "7z"],
        "preferred_format": "7z",
        "require_dat_verified": False,
        "upgrade_until_format": "7z",
    }
    base.update(overrides)
    return _QualityProfile(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T017 — format filter
# ---------------------------------------------------------------------------


def test_format_in_allowed_accepts(make_facts: Callable[..., ReleaseFacts]) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(), make_facts(file_format="raw")
    )
    assert result.decision is Decision.ACCEPT


def test_format_not_allowed_rejects(make_facts: Callable[..., ReleaseFacts]) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(), make_facts(file_format="rar")
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "format_not_allowed"


# ---------------------------------------------------------------------------
# T018 — DAT requirement
# ---------------------------------------------------------------------------


def test_dat_required_rejects_unverified(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(require_dat_verified=True),
        make_facts(dat_verified=False),
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "dat_required"


def test_dat_required_accepts_verified(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(require_dat_verified=True),
        make_facts(dat_verified=True),
    )
    assert result.decision is Decision.ACCEPT


# ---------------------------------------------------------------------------
# T019 — cutoff_met (file_format == upgrade_until_format)
# ---------------------------------------------------------------------------


def test_cutoff_met_when_format_equals_upgrade_target(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(upgrade_until_format="7z"),
        make_facts(file_format="7z"),
    )
    assert result.decision is Decision.ACCEPT
    assert result.reason is not None
    assert result.reason.code == "cutoff_met"


def test_below_cutoff_accepted_but_no_cutoff_marker(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    result = ProfileEvaluator.evaluate_quality(
        _profile(upgrade_until_format="7z"),
        make_facts(file_format="raw"),
    )
    assert result.decision is Decision.ACCEPT
    assert result.reason is not None
    assert result.reason.code == "format_allowed"
