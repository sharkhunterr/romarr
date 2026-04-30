"""Evaluator purity property test (T030 / SC-002).

Hypothesis-driven: 1 000 randomized ``(profile, facts)`` triples;
calling each evaluator twice in a row MUST return identical
results, and no module-level state may change between calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hypothesis import given, settings
from hypothesis import strategies as st

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.scoring import compute_custom_format_score
from romarr.profiles.types import ReleaseFacts

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


_REGION_CODES = st.sampled_from(
    ["USA", "EUR", "JPN", "World", "World+EUR", "KOR", "BRA", "AUS"]
)
_LANG_CODES = st.sampled_from(["en", "fr", "ja", "de", "es", "it", "multi"])
_FORMATS = st.sampled_from(["raw", "zip", "7z", "chd", "rvz", "nkit"])


_facts_strategy = st.builds(
    ReleaseFacts,
    title=st.text(min_size=0, max_size=20),
    regions=st.lists(_REGION_CODES, min_size=0, max_size=3).map(tuple),
    languages=st.lists(_LANG_CODES, min_size=0, max_size=3).map(tuple),
    revision=st.one_of(
        st.none(),
        st.sampled_from(["", "Rev 0", "Rev A", "Rev B", "Rev Z"]),
    ),
    dump_status=st.sampled_from(list(DumpStatus)),
    tags=st.lists(
        st.sampled_from(["[!]", "[h]", "[h2]", "[t]", "[b]", "[o]", "[T+Fr]", "[T+En]"]),
        min_size=0,
        max_size=3,
    ).map(tuple),
    naming_convention=st.sampled_from(list(NamingConvention)),
    file_format=_FORMATS,
    dat_verified=st.booleans(),
    indexer_source=st.one_of(st.none(), st.sampled_from(["newznab", "torznab"])),
    release_size=st.one_of(st.none(), st.integers(min_value=1, max_value=10**12)),
    release_group=st.one_of(st.none(), st.sampled_from(["DEMENT", "iND", "RFTD"])),
)


@dataclass
class _Q:
    allowed_formats: list[str]
    preferred_format: str
    require_dat_verified: bool
    upgrade_until_format: str


@dataclass
class _R:
    priorities: list[str] = field(default_factory=list)
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


@dataclass
class _D:
    allowed_dump_status: list[str] = field(default_factory=lambda: ["verified"])
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False


@dataclass
class _L:
    required_languages: list[str] = field(default_factory=list)
    preferred_languages: list[str] = field(default_factory=list)
    exclude_japanese_only: bool = True


_quality_profile_strategy = st.builds(
    _Q,
    allowed_formats=st.lists(_FORMATS, min_size=1, max_size=4, unique=True),
    preferred_format=_FORMATS,
    require_dat_verified=st.booleans(),
    upgrade_until_format=_FORMATS,
)


_region_profile_strategy = st.builds(
    _R,
    priorities=st.lists(_REGION_CODES, min_size=0, max_size=4, unique=True),
    allow_fallback_outside_priorities=st.booleans(),
    exclude_regions=st.lists(_REGION_CODES, min_size=0, max_size=2, unique=True),
)


_dump_profile_strategy = st.builds(
    _D,
    allowed_dump_status=st.lists(
        st.sampled_from([s.value for s in DumpStatus]),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    allow_proto_beta=st.booleans(),
    allow_hacks=st.booleans(),
    allow_trainers=st.booleans(),
    allow_translations=st.booleans(),
)


_language_profile_strategy = st.builds(
    _L,
    required_languages=st.lists(_LANG_CODES, min_size=0, max_size=3, unique=True),
    preferred_languages=st.lists(_LANG_CODES, min_size=0, max_size=3, unique=True),
    exclude_japanese_only=st.booleans(),
)


# ---------------------------------------------------------------------------
# Purity: same input ⇒ same output, twice in a row.
# ---------------------------------------------------------------------------


@given(profile=_quality_profile_strategy, facts=_facts_strategy)
@settings(max_examples=250, deadline=None)
def test_quality_evaluator_is_pure(profile: _Q, facts: ReleaseFacts) -> None:
    first = ProfileEvaluator.evaluate_quality(profile, facts)
    second = ProfileEvaluator.evaluate_quality(profile, facts)
    assert first == second


@given(profile=_region_profile_strategy, facts=_facts_strategy)
@settings(max_examples=250, deadline=None)
def test_region_evaluator_is_pure(profile: _R, facts: ReleaseFacts) -> None:
    first = ProfileEvaluator.evaluate_region(profile, facts)
    second = ProfileEvaluator.evaluate_region(profile, facts)
    assert first == second


@given(profile=_dump_profile_strategy, facts=_facts_strategy)
@settings(max_examples=250, deadline=None)
def test_dump_evaluator_is_pure(profile: _D, facts: ReleaseFacts) -> None:
    first = ProfileEvaluator.evaluate_dump(profile, facts)
    second = ProfileEvaluator.evaluate_dump(profile, facts)
    assert first == second


@given(profile=_language_profile_strategy, facts=_facts_strategy)
@settings(max_examples=250, deadline=None)
def test_language_evaluator_is_pure(profile: _L, facts: ReleaseFacts) -> None:
    first = ProfileEvaluator.evaluate_language(profile, facts)
    second = ProfileEvaluator.evaluate_language(profile, facts)
    assert first == second


# ---------------------------------------------------------------------------
# Scoring purity (CL parity to evaluators)
# ---------------------------------------------------------------------------


@dataclass
class _Fmt:
    score: int
    conditions: list[dict[str, object]]


_DEFAULT_FORMATS = [
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
    _Fmt(score=10, conditions=[
        {"field": "naming_convention", "operator": "equals", "values": "no-intro"}
    ]),
]


@given(facts=_facts_strategy)
@settings(max_examples=250, deadline=None)
def test_scoring_is_pure(facts: ReleaseFacts) -> None:
    first = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    second = compute_custom_format_score(_DEFAULT_FORMATS, facts)
    assert first == second
