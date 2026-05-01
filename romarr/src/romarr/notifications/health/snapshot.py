"""Aggregate per-component health into a :class:`HealthSnapshot`.

The dashboard / API need a one-shot view of "is the system OK
right now?" with a per-component drill-down. This module builds
that aggregate from the ``health_check`` table's current rows.

The aggregation rule is **worst-of**: if any component reports
``error``, ``overall_status = error``; else if any reports
``warning``, ``overall_status = warning``; else ``ok``. This
matches operator intuition — one broken indexer makes the
system "not fully healthy" even when everything else is fine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthSnapshot,
    HealthStatus,
)


def build_snapshot(
    *,
    results: list[HealthCheckResult],
    refreshed_at: datetime | None = None,
) -> HealthSnapshot:
    """Group ``results`` by category and pick the worst-of overall.

    ``refreshed_at`` defaults to ``datetime.now(UTC)`` so the
    caller doesn't need a clock; tests pass an explicit value
    for reproducibility.
    """
    by_category: dict[ComponentCategory, list[HealthCheckResult]] = {}
    for result in results:
        by_category.setdefault(result.category, []).append(result)

    return HealthSnapshot(
        overall_status=_worst_of([r.status for r in results]),
        by_category=by_category,
        refreshed_at=refreshed_at or datetime.now(UTC),
    )


# ``_RANK`` orders the three statuses from healthiest (low) to
# worst (high); the snapshot picks the highest rank seen across
# all components.
_RANK: dict[HealthStatus, int] = {
    HealthStatus.OK: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.ERROR: 2,
}


def _worst_of(statuses: list[HealthStatus]) -> HealthStatus:
    if not statuses:
        return HealthStatus.OK
    return max(statuses, key=_RANK.__getitem__)


__all__ = ["build_snapshot"]
