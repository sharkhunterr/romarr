"""DAT freshness health check (T045, FR-019).

The DAT files (No-Intro / Redump / TOSEC) must be refreshed
periodically — an outdated DAT means new releases land in
``unidentified_dump`` purgatory until the next refresh. This
check warns the operator when the most-recent DAT update is
more than 30 days old, errors at 90+ days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

_WARNING_AFTER = timedelta(days=30)
_ERROR_AFTER = timedelta(days=90)


@dataclass
class DatFreshnessHealthCheck:
    """Compares the DAT's ``last_updated_at`` to wall-clock now.

    Each (source, platform) DAT is its own component instance —
    e.g. ``dat:no-intro:megadrive`` — so the operator's UI can
    show which packs are stale without aggregating across the
    whole DAT layer.
    """

    component_id: str
    last_updated_at: datetime
    category: ComponentCategory = ComponentCategory.DAT
    now_factory: type[datetime] = datetime  # injectable for tests

    async def run(self) -> HealthCheckResult:
        now = self.now_factory.now(UTC)
        age = now - self.last_updated_at
        if age >= _ERROR_AFTER:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=(
                    f"DAT {age.days}d old (≥{_ERROR_AFTER.days}d threshold)"
                ),
            )
        if age >= _WARNING_AFTER:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.WARNING,
                message=(
                    f"DAT {age.days}d old (≥{_WARNING_AFTER.days}d threshold)"
                ),
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=f"DAT {age.days}d old",
        )


__all__ = ["DatFreshnessHealthCheck"]
