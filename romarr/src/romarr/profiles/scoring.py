"""Custom Format scoring (Phase 3 — pure-function complement to the evaluator).

Given a list of Custom Formats and a :class:`ReleaseFacts` snapshot,
return the cumulative score. A format contributes its ``score`` to
the sum iff ALL of its top-level conditions match; OR-grouping
within a single condition (``or: [...]``) lets a condition match
when ANY of its sub-conditions matches (FR-021).

The operator dispatch table is closed (no plugin path) — every
operator is one of the seven literal values declared in
:class:`romarr.profiles.types.ConditionOperator`. Adversarial
``matches_regex`` patterns are vetted at SAVE time by
:class:`CustomFormatCondition` (Pydantic-side regex compile in
:mod:`romarr.profiles.schemas`) so the hot path here can rely on
already-compiled patterns without per-match runtime timeouts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from romarr.profiles.types import ReleaseFacts


class _CustomFormatShape(Protocol):
    """Anything that exposes ``score`` and ``conditions`` works.

    Both the SQLAlchemy model row and the Pydantic ``CustomFormatCreate``
    shape match this shape via attribute access — preview / dry-run
    paths can score against unsaved formats.
    """

    score: int
    conditions: Any


def compute_custom_format_score(
    formats: Iterable[_CustomFormatShape],
    facts: ReleaseFacts,
) -> int:
    """Return the cumulative score across all matching formats."""
    total = 0
    for fmt in formats:
        if _format_matches(fmt, facts):
            total += fmt.score
    return total


def _format_matches(
    fmt: _CustomFormatShape, facts: ReleaseFacts
) -> bool:
    raw_conditions = list(_iter_conditions(fmt.conditions))
    if not raw_conditions:
        return False
    return all(_condition_matches(cond, facts) for cond in raw_conditions)


def _iter_conditions(conditions: Any) -> Iterable[Mapping[str, Any]]:
    """Normalise the ``conditions`` shape (Pydantic or raw dict) to dicts.

    The SQLAlchemy column stores a JSON list of dicts; the Pydantic
    ``CustomFormatCondition`` exports the same shape via
    ``model_dump(by_alias=True)`` — ``or`` becomes the alias for ``or_``.
    """
    if conditions is None:
        return []
    out: list[Mapping[str, Any]] = []
    for entry in conditions:
        if isinstance(entry, Mapping):
            out.append(entry)
        elif hasattr(entry, "model_dump"):
            dumped = entry.model_dump(by_alias=True)
            out.append(dumped)
        else:  # pragma: no cover — caller already validated shape
            raise TypeError(f"unsupported condition entry: {entry!r}")
    return out


def _condition_matches(
    condition: Mapping[str, Any], facts: ReleaseFacts
) -> bool:
    """Top-level condition match. Handles OR-grouping (FR-021)."""
    if _single_condition_matches(condition, facts):
        return True
    or_branch = condition.get("or") or []
    return any(_single_condition_matches(branch, facts) for branch in or_branch)


def _single_condition_matches(
    condition: Mapping[str, Any], facts: ReleaseFacts
) -> bool:
    field_name = condition["field"]
    operator = condition["operator"]
    expected = condition["values"]
    actual = _extract(field_name, facts)
    return _OPERATORS[operator](actual, expected)


# ---------------------------------------------------------------------------
# Field accessors — each returns the comparable value(s) for one condition.
# ---------------------------------------------------------------------------


def _extract(field_name: str, facts: ReleaseFacts) -> Any:
    if field_name == "tags":
        return list(facts.tags)
    if field_name == "region":
        # A release may carry multiple region codes; conditions match
        # if the operator matches against ANY of them. We hand the list
        # to the operator dispatch which handles "any-of" semantics.
        return list(facts.regions)
    if field_name == "format":
        return facts.file_format
    if field_name == "dump_status":
        return facts.dump_status.value
    if field_name == "release_group":
        return facts.release_group
    if field_name == "indexer_source":
        return facts.indexer_source
    if field_name == "languages":
        return list(facts.languages)
    if field_name == "revision":
        return facts.revision or ""
    if field_name == "naming_convention":
        return facts.naming_convention.value
    if field_name == "release_size":
        return facts.release_size
    raise ValueError(f"unknown condition field: {field_name!r}")


# ---------------------------------------------------------------------------
# Operator dispatch
# ---------------------------------------------------------------------------


def _op_matches_regex(actual: Any, expected: Any) -> bool:
    pattern = re.compile(str(expected))
    if isinstance(actual, list):
        return any(pattern.search(str(item)) is not None for item in actual)
    if actual is None:
        return False
    return bool(pattern.search(str(actual)))


def _op_equals(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        return any(item == expected for item in actual)
    return bool(actual == expected)


def _op_in(actual: Any, expected: Any) -> bool:
    candidates: Sequence[Any] = expected if isinstance(expected, list | tuple) else [expected]
    if isinstance(actual, list):
        return any(item in candidates for item in actual)
    return actual in candidates


def _op_contains(actual: Any, expected: Any) -> bool:
    """Substring containment — actual contains the expected sub-string.

    For list-valued fields (``tags``, ``regions``, ``languages``)
    this means ``any(expected in item for item in actual)``.
    """
    expected_str = str(expected)
    if isinstance(actual, list):
        return any(expected_str in str(item) for item in actual)
    if actual is None:
        return False
    return expected_str in str(actual)


def _op_not_in(actual: Any, expected: Any) -> bool:
    return not _op_in(actual, expected)


def _op_greater_than(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    return float(actual) > float(expected)


def _op_less_than(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    return float(actual) < float(expected)


_OPERATORS = {
    "matches_regex": _op_matches_regex,
    "equals": _op_equals,
    "in": _op_in,
    "contains": _op_contains,
    "not_in": _op_not_in,
    "greater_than": _op_greater_than,
    "less_than": _op_less_than,
}


__all__ = ["compute_custom_format_score"]
