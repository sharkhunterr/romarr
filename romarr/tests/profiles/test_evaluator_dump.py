"""Dump evaluator tests (T023-T024)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from romarr.domain.enums import DumpStatus
from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.types import Decision, ReleaseFacts


@dataclass
class _DumpProfile:
    allowed_dump_status: list[str]
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False


# ---------------------------------------------------------------------------
# T023 — status filter
# ---------------------------------------------------------------------------


def test_allowed_status_accepted(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _DumpProfile(allowed_dump_status=["verified"])
    result = ProfileEvaluator.evaluate_dump(
        profile, make_facts(dump_status=DumpStatus.VERIFIED)
    )
    assert result.decision is Decision.ACCEPT


def test_disallowed_status_rejected(make_facts: Callable[..., ReleaseFacts]) -> None:
    profile = _DumpProfile(allowed_dump_status=["verified"])
    result = ProfileEvaluator.evaluate_dump(
        profile, make_facts(dump_status=DumpStatus.BADDUMP)
    )
    assert result.decision is Decision.REJECT
    assert result.reason is not None
    assert result.reason.code == "dump_status_disallowed"


# ---------------------------------------------------------------------------
# T024 — permissive flags table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "flag"),
    [
        (DumpStatus.HACK, "allow_hacks"),
        (DumpStatus.TRAINER, "allow_trainers"),
        (DumpStatus.TRANSLATION, "allow_translations"),
        (DumpStatus.PROTO, "allow_proto_beta"),
        (DumpStatus.BETA, "allow_proto_beta"),
    ],
)
def test_permissive_flag_accepts_status(
    status: DumpStatus, flag: str, make_facts: Callable[..., ReleaseFacts]
) -> None:
    profile = _DumpProfile(allowed_dump_status=["verified"], **{flag: True})
    result = ProfileEvaluator.evaluate_dump(profile, make_facts(dump_status=status))
    assert result.decision is Decision.ACCEPT
    assert result.reason is not None
    assert result.reason.code == "dump_status_permissive"


@pytest.mark.parametrize(
    "status",
    [DumpStatus.HACK, DumpStatus.TRAINER, DumpStatus.PROTO, DumpStatus.BETA],
)
def test_permissive_flag_off_rejects(
    status: DumpStatus, make_facts: Callable[..., ReleaseFacts]
) -> None:
    profile = _DumpProfile(allowed_dump_status=["verified"])  # all flags false
    result = ProfileEvaluator.evaluate_dump(profile, make_facts(dump_status=status))
    assert result.decision is Decision.REJECT


def test_baddump_never_permissive(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """No permissive flag covers BADDUMP — only the allowlist can let it through."""
    profile = _DumpProfile(
        allowed_dump_status=["verified"],
        allow_hacks=True,
        allow_trainers=True,
        allow_translations=True,
        allow_proto_beta=True,
    )
    result = ProfileEvaluator.evaluate_dump(
        profile, make_facts(dump_status=DumpStatus.BADDUMP)
    )
    assert result.decision is Decision.REJECT
