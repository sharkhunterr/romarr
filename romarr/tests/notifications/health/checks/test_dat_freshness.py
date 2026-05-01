"""DAT freshness check (T045, FR-019)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from romarr.notifications.health.checks.dat_freshness import (
    DatFreshnessHealthCheck,
)
from romarr.notifications.types import HealthStatus

_NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


class _FixedClock(datetime):
    """A datetime subclass whose ``.now`` returns a fixed
    instant — avoids freezegun for one assertion."""

    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return _NOW


@pytest.mark.asyncio
async def test_dat_31_days_old_emits_warning() -> None:
    last_updated = _NOW - timedelta(days=31)
    check = DatFreshnessHealthCheck(
        component_id="dat:no-intro:megadrive",
        last_updated_at=last_updated,
        now_factory=_FixedClock,
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert "31d" in (result.message or "")


@pytest.mark.asyncio
async def test_dat_91_days_old_emits_error() -> None:
    last_updated = _NOW - timedelta(days=91)
    check = DatFreshnessHealthCheck(
        component_id="dat:redump:psx",
        last_updated_at=last_updated,
        now_factory=_FixedClock,
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert "91d" in (result.message or "")


@pytest.mark.asyncio
async def test_dat_29_days_old_is_ok() -> None:
    last_updated = _NOW - timedelta(days=29)
    check = DatFreshnessHealthCheck(
        component_id="dat:no-intro:megadrive",
        last_updated_at=last_updated,
        now_factory=_FixedClock,
    )
    result = await check.run()
    assert result.status is HealthStatus.OK


@pytest.mark.asyncio
async def test_dat_at_exact_30_day_boundary_is_warning() -> None:
    """Boundary: 30 days exactly is ``warning`` (≥ threshold,
    not strictly greater)."""
    last_updated = _NOW - timedelta(days=30)
    check = DatFreshnessHealthCheck(
        component_id="dat:no-intro:megadrive",
        last_updated_at=last_updated,
        now_factory=_FixedClock,
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
