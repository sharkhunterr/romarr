"""DB connectivity health check (T047).

Issues ``SELECT 1`` against the configured async session. The
result is ``ok`` if the round-trip completes within the warning
threshold (default 1.0 s), ``warning`` if it's slow but still
responsive, ``error`` on any exception (driver, connection,
timeout).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_WARNING_THRESHOLD_SECONDS = 1.0


@dataclass
class DbHealthCheck:
    """Probes the database with a single ``SELECT 1`` query.

    The session factory is injected so tests can pass a
    deliberately-slow stub. ``warning_threshold_seconds``
    controls the ok/warning boundary; the engine's outer
    ``run_check`` timeout still applies for the error path.
    """

    session_factory: Callable[[], Awaitable[AsyncSession]]
    component_id: str = "db"
    category: ComponentCategory = ComponentCategory.DB
    warning_threshold_seconds: float = _DEFAULT_WARNING_THRESHOLD_SECONDS

    async def run(self) -> HealthCheckResult:
        start = time.monotonic()
        session = await self.session_factory()
        try:
            await session.execute(text("SELECT 1"))
        finally:
            await session.close()
        elapsed = time.monotonic() - start
        if elapsed >= self.warning_threshold_seconds:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.WARNING,
                message=(
                    f"DB round-trip slow: {elapsed:.2f}s "
                    f"(threshold {self.warning_threshold_seconds:.1f}s)"
                ),
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=f"DB round-trip {elapsed:.3f}s",
        )


__all__ = ["DbHealthCheck"]
