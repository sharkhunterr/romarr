"""Library path availability health check (T049).

A network mount that's gone silent is a common ops failure —
the FS layer hangs indefinitely on ``stat``. This check wraps
``os.stat`` in a 5 s timeout so a hung mount surfaces as
``error`` rather than blocking the whole cycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

_STAT_TIMEOUT_SECONDS = 5.0


@dataclass
class LibraryPathHealthCheck:
    """Probes ``self.path.stat()`` with a 5 s deadline.

    On timeout (a hung NFS / SMB mount, for instance), the
    result is ``error`` with reason ``timeout``. On a missing
    path, ``error`` with the OS error class. Otherwise ``ok``.
    """

    component_id: str
    path: Path
    category: ComponentCategory = ComponentCategory.LIBRARY
    timeout_seconds: float = _STAT_TIMEOUT_SECONDS

    async def run(self) -> HealthCheckResult:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.path.stat),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=(
                    f"timeout: stat exceeded "
                    f"{self.timeout_seconds:.0f}s"
                ),
            )
        except OSError as exc:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=f"{exc.__class__.__name__}: {exc}",
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=f"{self.path} reachable",
        )


__all__ = ["LibraryPathHealthCheck"]
