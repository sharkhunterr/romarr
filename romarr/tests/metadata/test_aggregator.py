"""Aggregator invariants (T048-T053).

The aggregator is pure: every test exercises ``aggregate(...)``
directly with hand-crafted inputs. The hypothesis-driven property
test pins the FR-009 additive-merge invariant — the constitutional
anti-RomM-#1770 mechanism.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from romarr.metadata import (
    AggregationResult,
    GameMetadata,
    ProviderField,
    aggregate,
)


def _meta(provider_name: str, **fields: Any) -> GameMetadata:
    return GameMetadata(
        provider_name=provider_name,
        provider_game_id=fields.pop("provider_game_id", "1"),
        fields={ProviderField(k): v for k, v in fields.items()},
        cover_url=None,
        fetched_at=datetime(2026, 4, 29, tzinfo=UTC),
    )


def _priority(*pairs: tuple[str, str]) -> list[tuple[str, int, str]]:
    """Build a field-priority projection from ``(field, provider)`` pairs.

    Pairs MUST be in priority order — this helper assigns sequential
    ``priority_order`` values starting from 1 per field.
    """
    out: list[tuple[str, int, str]] = []
    seen: dict[str, int] = {}
    for field_name, provider_name in pairs:
        seen[field_name] = seen.get(field_name, 0) + 1
        out.append((field_name, seen[field_name], provider_name))
    return out


# ---------------------------------------------------------------------------
# T048 — locked field never overwritten (FR-010, US2)
# ---------------------------------------------------------------------------


def test_locked_field_blocks_overwrite() -> None:
    fp = _priority(("title", "igdb"))
    cached = {"igdb": _meta("igdb", title="IGDB Title")}
    result = aggregate(
        game_id=1,
        locked_fields={"title"},
        cached=cached,
        field_priority=fp,
        existing={ProviderField.TITLE: "Operator's Title"},
    )
    # Locked: result carries the existing value, NOT the IGDB one.
    assert result.fields[ProviderField.TITLE] == ("Operator's Title", "<locked>")
    assert ProviderField.TITLE in result.skipped_locked


def test_locked_field_with_no_existing_no_provider_value_omitted() -> None:
    fp = _priority(("title", "igdb"))
    result = aggregate(
        game_id=2,
        locked_fields={"title"},
        cached={},
        field_priority=fp,
        existing={},
    )
    assert ProviderField.TITLE not in result.fields
    assert ProviderField.TITLE not in result.skipped_locked


# ---------------------------------------------------------------------------
# T049 — additive: never null an existing non-locked value (FR-009, US3)
# ---------------------------------------------------------------------------


def test_additive_merge_keeps_existing_when_no_provider_contributes() -> None:
    fp = _priority(("summary", "igdb"))
    # IGDB has a cache entry but the summary slot is empty.
    cached = {"igdb": _meta("igdb", title="ignored")}
    result = aggregate(
        game_id=3,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
        existing={ProviderField.SUMMARY: "Existing summary"},
    )
    # The aggregator preserves the existing summary.
    assert result.fields[ProviderField.SUMMARY] == ("Existing summary", "<existing>")


def test_additive_merge_zero_is_a_real_value() -> None:
    """rating=0.0 / players=0 is a contribution, not "empty"."""
    fp = _priority(("rating", "igdb"))
    cached = {"igdb": _meta("igdb", rating=0.0)}
    result = aggregate(
        game_id=4,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.fields[ProviderField.RATING] == (0.0, "igdb")


# ---------------------------------------------------------------------------
# T050 — priority winner is the highest-ranked provider with a value
# ---------------------------------------------------------------------------


def test_higher_priority_provider_wins() -> None:
    fp = _priority(("summary", "igdb"), ("summary", "mobygames"))
    cached = {
        "igdb": _meta("igdb", summary="IGDB"),
        "mobygames": _meta("mobygames", summary="MobyGames"),
    }
    result = aggregate(
        game_id=5,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.fields[ProviderField.SUMMARY] == ("IGDB", "igdb")


def test_lower_priority_wins_when_higher_has_no_value() -> None:
    """Higher-priority provider returned nothing → fall through to next."""
    fp = _priority(("summary", "igdb"), ("summary", "mobygames"))
    cached = {
        "igdb": _meta("igdb", title="ignored"),  # no summary
        "mobygames": _meta("mobygames", summary="MobyGames"),
    }
    result = aggregate(
        game_id=6,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.fields[ProviderField.SUMMARY] == ("MobyGames", "mobygames")


def test_provider_not_in_cache_is_skipped() -> None:
    fp = _priority(("summary", "igdb"), ("summary", "mobygames"))
    cached = {
        "mobygames": _meta("mobygames", summary="MobyGames"),
    }  # IGDB never cached
    result = aggregate(
        game_id=7,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.fields[ProviderField.SUMMARY] == ("MobyGames", "mobygames")


# ---------------------------------------------------------------------------
# T053 — all empty → needs_metadata_refresh = True (FR-013)
# ---------------------------------------------------------------------------


def test_all_providers_empty_sets_refresh_flag() -> None:
    fp = _priority(("title", "igdb"), ("summary", "igdb"))
    cached = {"igdb": _meta("igdb")}  # zero contributions
    result = aggregate(
        game_id=8,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.needs_metadata_refresh is True
    assert result.fields == {}


def test_at_least_one_contribution_clears_refresh_flag() -> None:
    fp = _priority(("title", "igdb"))
    cached = {"igdb": _meta("igdb", title="Sonic")}
    result = aggregate(
        game_id=9,
        locked_fields=set(),
        cached=cached,
        field_priority=fp,
    )
    assert result.needs_metadata_refresh is False


# ---------------------------------------------------------------------------
# T051 — priority change requires zero new API calls (FR-012)
#
# This is exercised purely against the aggregator's pure function: same
# cached input + new priority → new winners, no provider hit. The
# orchestrator-side "no respx call" assertion is in test_refresh.py
# when the orchestrator lands.
# ---------------------------------------------------------------------------


def test_priority_change_picks_new_winner_from_same_cache() -> None:
    cached = {
        "igdb": _meta("igdb", summary="IGDB"),
        "mobygames": _meta("mobygames", summary="MobyGames"),
    }

    fp_a = _priority(("summary", "igdb"), ("summary", "mobygames"))
    fp_b = _priority(("summary", "mobygames"), ("summary", "igdb"))

    a = aggregate(game_id=10, locked_fields=set(), cached=cached, field_priority=fp_a)
    b = aggregate(game_id=10, locked_fields=set(), cached=cached, field_priority=fp_b)

    assert a.fields[ProviderField.SUMMARY] == ("IGDB", "igdb")
    assert b.fields[ProviderField.SUMMARY] == ("MobyGames", "mobygames")


# ---------------------------------------------------------------------------
# T052 — property-based additive-merge invariant
# ---------------------------------------------------------------------------


_NON_EMPTY_STRINGS = st.text(min_size=1, max_size=20)


@given(
    a_summary=st.one_of(st.none(), _NON_EMPTY_STRINGS),
    b_summary=st.one_of(st.none(), _NON_EMPTY_STRINGS),
    existing_summary=st.one_of(st.none(), _NON_EMPTY_STRINGS),
    locked=st.booleans(),
)
def test_property_additive_merge(
    a_summary: str | None,
    b_summary: str | None,
    existing_summary: str | None,
    locked: bool,
) -> None:
    """For any combination of provider contributions and existing
    state, the result MUST satisfy the invariant: a previously
    non-empty, non-locked summary is NEVER nulled."""
    fp = _priority(("summary", "a"), ("summary", "b"))
    cached: dict[str, GameMetadata] = {}
    if a_summary is not None:
        cached["a"] = _meta("a", summary=a_summary)
    if b_summary is not None:
        cached["b"] = _meta("b", summary=b_summary)

    locked_set: set[str] = {"summary"} if locked else set()
    existing: dict[ProviderField, Any] = {}
    if existing_summary is not None:
        existing[ProviderField.SUMMARY] = existing_summary

    result = aggregate(
        game_id=11,
        locked_fields=locked_set,
        cached=cached,
        field_priority=fp,
        existing=existing,
    )

    if existing_summary is not None:
        # Pre-existing non-empty value: MUST survive unless it's
        # explicitly overwritten by a winning provider.
        if locked:
            # Locked: existing carried verbatim.
            assert result.fields[ProviderField.SUMMARY][0] == existing_summary
            assert result.fields[ProviderField.SUMMARY][1] == "<locked>"
        elif a_summary is not None:
            assert result.fields[ProviderField.SUMMARY] == (a_summary, "a")
        elif b_summary is not None:
            assert result.fields[ProviderField.SUMMARY] == (b_summary, "b")
        else:
            # No provider contributed → existing carried forward.
            assert result.fields[ProviderField.SUMMARY] == (
                existing_summary,
                "<existing>",
            )


# ---------------------------------------------------------------------------
# Empty / pathological inputs
# ---------------------------------------------------------------------------


def test_empty_field_priority_yields_empty_result() -> None:
    result = aggregate(
        game_id=12,
        locked_fields=set(),
        cached={},
        field_priority=[],
    )
    assert isinstance(result, AggregationResult)
    assert result.fields == {}
    assert result.needs_metadata_refresh is True


@pytest.mark.parametrize("empty", ["", [], (), {}, None])
def test_empty_values_are_skipped(empty: Any) -> None:
    fp = _priority(("title", "igdb"))
    cached = {"igdb": _meta("igdb", title=empty) if empty != [] else _meta("igdb")}
    # When value is None / empty, the aggregator should treat it as "no contribution".
    if empty is not None and empty != []:
        cached = {"igdb": _meta("igdb")}
        cached["igdb"].fields[ProviderField.TITLE] = empty
    result = aggregate(
        game_id=13, locked_fields=set(), cached=cached, field_priority=fp
    )
    assert ProviderField.TITLE not in result.fields
    assert result.needs_metadata_refresh is True
