"""The lock-aware, additive, per-field priority merger.

This module is the constitutional core of spec 002. Two invariants
MUST hold for every aggregation:

  1. **Lock-aware** (FR-010, US2): a field listed in the Game's
     ``locked_fields`` is never considered, never overwritten. The
     persisted value is preserved verbatim.
  2. **Additive** (FR-009, US3): re-aggregation NEVER nulls a
     previously-populated, non-locked field. If the new winning
     provider returns no value for a field where an earlier provider
     contributed something, the earlier value is kept. Only the
     positive case (new winner has a non-empty value with strictly
     higher priority) overwrites.

The aggregator is **pure** — no DB writes, no HTTP, no clock. It takes
the union of cached provider responses, the field-priority table, the
Game's ``locked_fields``, and (optionally) the Game's current persisted
values for the fields, and returns an :class:`AggregationResult` that
the caller applies to the Game in a single transaction.

Property-based tests in ``tests/metadata/test_aggregator.py`` use
hypothesis to fuzz the additive-merge invariant.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from romarr.metadata.types import (
    AggregationResult,
    GameMetadata,
    ProviderField,
)


def _is_empty(value: Any) -> bool:
    """The "no contribution" predicate.

    Empty strings, empty lists/sets/dicts, and None all count as "no
    contribution". 0, False, and 0.0 do NOT — they are valid values
    (e.g. ``rating = 0.0`` is a real signal). The test:
    ``value is None or (hasattr(value, "__len__") and len(value) == 0)``.
    """
    if value is None:
        return True
    if isinstance(value, str | list | tuple | set | frozenset | dict):
        return len(value) == 0
    return False


def _ranking_for(
    field: ProviderField,
    field_priority: Iterable[tuple[str, int, str]],
) -> list[str]:
    """Return the providers ranked for ``field``, lowest order first.

    ``field_priority`` is iterable of ``(field_name, priority_order,
    provider_name)`` triples — exactly the projection the migration
    seeds. Providers absent from the ranking are excluded.
    """
    rows = sorted(
        (row for row in field_priority if row[0] == field.value),
        key=lambda r: r[1],
    )
    return [r[2] for r in rows]


def aggregate(
    *,
    game_id: int,
    locked_fields: Iterable[str],
    cached: Mapping[str, GameMetadata],
    field_priority: Iterable[tuple[str, int, str]],
    existing: Mapping[ProviderField, Any] | None = None,
) -> AggregationResult:
    """Compute a fresh :class:`AggregationResult` for ``game_id``.

    Parameters
    ----------
    game_id:
        Pass-through, written into the result.
    locked_fields:
        Iterable of canonical field names (string form of
        :class:`ProviderField`) that MUST NOT be touched.
    cached:
        Mapping ``provider_name → GameMetadata``. The aggregator only
        consults a provider that has a cached entry for this Game;
        missing providers are treated as "no contribution".
    field_priority:
        Iterable of ``(field_name, priority_order, provider_name)``
        triples. Typically the projection of the ``field_priority``
        table; the aggregator does NOT load it itself.
    existing:
        Optional mapping of the Game's current persisted field values.
        Used to enforce the additive invariant: when no enabled
        provider contributes, the Game's existing value (if any) is
        carried into ``fields`` so the caller's "apply to Game" pass
        does not regress to NULL.

    Returns
    -------
    AggregationResult
        ``fields`` carries ``(value, winning_provider_name)`` per
        field that has a value. ``skipped_locked`` lists every locked
        field that had a non-empty contribution somewhere in the
        cache. ``needs_metadata_refresh`` is True iff every contribut-
        able field came up empty across all enabled providers (no
        cached entry contributed anything, even pre-existing values
        are considered) — FR-013.
    """
    locked = {str(f) for f in locked_fields}
    existing_map: Mapping[ProviderField, Any] = existing or {}
    out_fields: dict[ProviderField, tuple[Any, str]] = {}
    skipped: list[ProviderField] = []
    cover_path: str | None = None

    any_provider_contributed = False

    for field in ProviderField:
        ranking = _ranking_for(field, field_priority)
        if not ranking:
            continue

        # Look for the highest-priority provider that has a cached,
        # non-empty value.
        winner_value: Any = None
        winner_name: str | None = None
        for provider_name in ranking:
            entry = cached.get(provider_name)
            if entry is None:
                continue
            value = entry.fields.get(field)
            if not _is_empty(value):
                winner_value = value
                winner_name = provider_name
                any_provider_contributed = True
                break

        if field.value in locked:
            # Locked: never write a new value, never null an existing
            # one. Surface the locked field if a provider tried to
            # contribute (operator visibility).
            if winner_name is not None:
                skipped.append(field)
            existing_value = existing_map.get(field)
            if not _is_empty(existing_value):
                # Carry the persisted value forward so the caller's
                # apply-result pass does not zero it.
                out_fields[field] = (existing_value, "<locked>")
            continue

        if winner_name is not None:
            out_fields[field] = (winner_value, winner_name)
            continue

        # No provider contributed — fall back to the existing value to
        # honour the additive invariant (FR-009).
        existing_value = existing_map.get(field)
        if not _is_empty(existing_value):
            out_fields[field] = (existing_value, "<existing>")

    needs_refresh = not any_provider_contributed

    # Cover path is set elsewhere (the refresh orchestrator stamps the
    # filesystem path on disk after a successful download). The
    # aggregator only forwards the field-side cover URL via the
    # ``COVER`` ProviderField; the ``cover_path`` slot in the result
    # exists for the orchestrator to fill in before persistence.
    return AggregationResult(
        game_id=game_id,
        fields=out_fields,
        skipped_locked=skipped,
        cover_path=cover_path,
        needs_metadata_refresh=needs_refresh,
    )
