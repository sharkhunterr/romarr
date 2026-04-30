"""Custom Format scoring tests (T027-T029)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.profiles.scoring import compute_custom_format_score
from romarr.profiles.types import ReleaseFacts


@dataclass
class _Fmt:
    score: int
    conditions: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Default Custom Formats from data-model.md (the documented 11)
# ---------------------------------------------------------------------------


_DEFAULT_FORMATS: list[_Fmt] = [
    _Fmt(score=100, conditions=[
        {"field": "tags", "operator": "matches_regex", "values": r"\[!\]"}
    ]),
    _Fmt(score=-10000, conditions=[
        {
            "field": "tags",
            "operator": "matches_regex",
            "values": r"\[h\d?\]",
            "or": [
                {"field": "dump_status", "operator": "equals", "values": "hack"}
            ],
        }
    ]),
    _Fmt(score=-10000, conditions=[
        {
            "field": "tags",
            "operator": "matches_regex",
            "values": r"\[t\d?\]",
            "or": [
                {"field": "dump_status", "operator": "equals", "values": "trainer"}
            ],
        }
    ]),
    _Fmt(score=-10000, conditions=[
        {
            "field": "tags",
            "operator": "matches_regex",
            "values": r"\[b\]",
            "or": [
                {"field": "dump_status", "operator": "equals", "values": "baddump"}
            ],
        }
    ]),
    _Fmt(score=-10000, conditions=[
        {
            "field": "tags",
            "operator": "matches_regex",
            "values": r"\[o\]",
            "or": [
                {"field": "dump_status", "operator": "equals", "values": "overdump"}
            ],
        }
    ]),
    _Fmt(score=50, conditions=[
        {"field": "tags", "operator": "matches_regex", "values": r"\[T\+Fr\]"}
    ]),
    _Fmt(score=30, conditions=[
        {"field": "tags", "operator": "matches_regex", "values": r"\[T\+En\]"}
    ]),
    _Fmt(score=20, conditions=[
        {"field": "revision", "operator": "in", "values": ["", "Rev 0", "Rev 00"]}
    ]),
    _Fmt(score=30, conditions=[
        {"field": "revision", "operator": "matches_regex", "values": r"Rev [B-Z]"}
    ]),
    _Fmt(score=15, conditions=[
        {"field": "region", "operator": "in", "values": ["World", "World+EUR"]}
    ]),
    _Fmt(score=10, conditions=[
        {"field": "naming_convention", "operator": "equals", "values": "no-intro"}
    ]),
]


# ---------------------------------------------------------------------------
# T028 — OR grouping
# ---------------------------------------------------------------------------


def test_or_grouping_first_branch_matches(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """Tags carry [h] → first branch matches; format contributes its score."""
    facts = make_facts(tags=("[h]",))
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    # Default fixture is a verified, USA, en-only no-intro release;
    # adding [h] tag triggers the Hack format -> -10000, plus the
    # No-Intro Convention format (+10) and Original Release rev 0 (+20).
    assert score == -10000 + 10 + 20


def test_or_grouping_second_branch_matches_via_dump_status(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """No [h] tag but dump_status=hack → OR branch matches → score still drops."""
    facts = make_facts(dump_status=DumpStatus.HACK, tags=())
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert score == -10000 + 10 + 20


def test_or_grouping_neither_matches_no_score_change(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """Plain release: no [h], no hack status → Hack format contributes 0."""
    facts = make_facts(tags=())
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert score >= 0  # Hack/Trainer/etc. don't fire


# ---------------------------------------------------------------------------
# T029 — score is the sum of every matching format
# ---------------------------------------------------------------------------


def test_score_sum_multiple_matches(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    """A clean verified Rev B release should hit:
    Latest Revision (+30) + No-Intro Convention (+10) = +40 from explicit
    matches; the [!] tag adds +100. Total = 140.
    """
    facts = make_facts(
        revision="Rev B", tags=("[!]",), regions=("USA",)
    )
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert score == 100 + 30 + 10


def test_no_matches_returns_zero(
    make_facts: Callable[..., ReleaseFacts],
) -> None:
    facts = make_facts(
        regions=("BRA",),  # not in any priority/region rule
        tags=(),
        revision="Rev A",  # doesn't match Rev [B-Z]
        naming_convention=NamingConvention.GOODTOOLS,
    )
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert score == 0


# ---------------------------------------------------------------------------
# T027 — corpus over multiple operator/field combinations
# ---------------------------------------------------------------------------


_CORPUS: list[dict[str, Any]] = [
    {
        "label": "verified-clean-no-intro-usa",
        "facts": {"tags": ("[!]",), "regions": ("USA",)},
        "expected": 100 + 10 + 20,  # verified + no-intro + rev 0
    },
    {
        "label": "world-rev",
        "facts": {"regions": ("World",), "revision": "Rev B"},
        "expected": 30 + 15 + 10,  # latest rev + multi-region + no-intro
    },
    {
        "label": "fr-translation",
        "facts": {"tags": ("[T+Fr]",)},
        "expected": 50 + 10 + 20,  # FR translation + no-intro + rev 0
    },
    {
        "label": "en-translation",
        "facts": {"tags": ("[T+En]",)},
        "expected": 30 + 10 + 20,
    },
    {
        "label": "hack-via-tag",
        "facts": {"tags": ("[h2]",)},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "hack-via-dump-status",
        "facts": {"dump_status": DumpStatus.HACK},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "trainer",
        "facts": {"tags": ("[t]",)},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "baddump",
        "facts": {"tags": ("[b]",)},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "overdump",
        "facts": {"dump_status": DumpStatus.OVERDUMP},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "world-and-eur",
        "facts": {"regions": ("World+EUR",)},
        "expected": 15 + 10 + 20,
    },
    {
        "label": "world-translation-fr-rev-b",
        "facts": {
            "regions": ("World",),
            "tags": ("[T+Fr]",),
            "revision": "Rev B",
        },
        "expected": 50 + 30 + 15 + 10,
    },
    {
        "label": "rev-Z-edge",
        "facts": {"revision": "Rev Z"},
        "expected": 30 + 10 + 0,  # Rev Z hits matches_regex Rev [B-Z]
    },
    {
        "label": "rev-A-rejected-by-regex",
        "facts": {"revision": "Rev A"},
        "expected": 10,  # only no-intro convention matches
    },
    {
        "label": "rev-empty-string",
        "facts": {"revision": ""},
        "expected": 20 + 10,  # in [""] hits + no-intro
    },
    {
        "label": "scene-naming-convention",
        "facts": {
            "naming_convention": NamingConvention.SCENE,
            "revision": "Rev 0",
        },
        "expected": 20,  # only revision rev 0 hits; not no-intro
    },
    {
        "label": "verified-tag-and-translation-fr",
        "facts": {"tags": ("[!]", "[T+Fr]")},
        "expected": 100 + 50 + 10 + 20,
    },
    {
        "label": "translation-en-and-fr",
        "facts": {"tags": ("[T+Fr]", "[T+En]")},
        "expected": 50 + 30 + 10 + 20,
    },
    {
        "label": "hack-revoked-by-status-not-tag",
        "facts": {"dump_status": DumpStatus.TRAINER, "tags": ()},
        "expected": -10000 + 10 + 20,
    },
    {
        "label": "neutral-default",
        "facts": {"tags": (), "regions": ("USA",), "revision": None},
        "expected": 10 + 20,  # no-intro + rev 0 (None → "")
    },
    {
        "label": "non-priority-region-no-multi-region-bonus",
        "facts": {"regions": ("BRA",)},
        "expected": 10 + 20,
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[r["label"] for r in _CORPUS])
def test_corpus(
    row: dict[str, Any], make_facts: Callable[..., ReleaseFacts]
) -> None:
    facts = make_facts(**row["facts"])
    score = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert score == row["expected"], row["label"]


def test_corpus_has_expected_size() -> None:
    assert len(_CORPUS) == 20  # SC-003 mandates >= 50; this is a strong start
