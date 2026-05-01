"""Snapshot aggregation tests (T053)."""

from __future__ import annotations

from datetime import UTC, datetime

from romarr.notifications.health.snapshot import build_snapshot
from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)


def _result(
    *,
    component: str,
    status: HealthStatus,
    category: ComponentCategory = ComponentCategory.INDEXER,
) -> HealthCheckResult:
    return HealthCheckResult(
        component=component,
        category=category,
        status=status,
        message=None,
    )


def test_overall_status_is_worst_component() -> None:
    """One ``error`` component dominates several ``ok`` and
    ``warning`` siblings (T053)."""
    results = [
        _result(component="db", status=HealthStatus.OK, category=ComponentCategory.DB),
        _result(component="library:Cartridges", status=HealthStatus.WARNING, category=ComponentCategory.LIBRARY),
        _result(component="indexer:slow", status=HealthStatus.ERROR),
        _result(component="metadata:igdb", status=HealthStatus.OK, category=ComponentCategory.METADATA),
    ]
    snapshot = build_snapshot(results=results)
    assert snapshot.overall_status is HealthStatus.ERROR


def test_overall_status_warning_when_no_errors() -> None:
    results = [
        _result(component="db", status=HealthStatus.OK, category=ComponentCategory.DB),
        _result(component="dat:no-intro", status=HealthStatus.WARNING, category=ComponentCategory.DAT),
    ]
    snapshot = build_snapshot(results=results)
    assert snapshot.overall_status is HealthStatus.WARNING


def test_overall_status_ok_when_all_ok() -> None:
    results = [
        _result(component="db", status=HealthStatus.OK, category=ComponentCategory.DB),
        _result(component="indexer:Y", status=HealthStatus.OK),
    ]
    snapshot = build_snapshot(results=results)
    assert snapshot.overall_status is HealthStatus.OK


def test_overall_status_ok_when_results_empty() -> None:
    """A fresh database before the first cycle reports ok rather
    than failing the whole snapshot."""
    snapshot = build_snapshot(results=[])
    assert snapshot.overall_status is HealthStatus.OK
    assert snapshot.by_category == {}


def test_by_category_groups_results() -> None:
    results = [
        _result(component="indexer:A", status=HealthStatus.OK),
        _result(component="indexer:B", status=HealthStatus.WARNING),
        _result(component="db", status=HealthStatus.OK, category=ComponentCategory.DB),
    ]
    snapshot = build_snapshot(results=results)
    assert ComponentCategory.INDEXER in snapshot.by_category
    assert len(snapshot.by_category[ComponentCategory.INDEXER]) == 2
    assert len(snapshot.by_category[ComponentCategory.DB]) == 1


def test_refreshed_at_uses_provided_value() -> None:
    fixed = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    snapshot = build_snapshot(results=[], refreshed_at=fixed)
    assert snapshot.refreshed_at == fixed


def test_refreshed_at_defaults_to_now() -> None:
    before = datetime.now(UTC)
    snapshot = build_snapshot(results=[])
    after = datetime.now(UTC)
    assert before <= snapshot.refreshed_at <= after
