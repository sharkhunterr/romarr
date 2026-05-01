"""Disk space health check (T046, FR-020).

For each library path, compares free space against the
configured ``min_disk_free_gb``:

  * free ≥ ``min x 1.5``  →  ``ok``
  * ``min`` ≤ free < ``min x 1.5``  →  ``warning``
  * free < ``min``  →  ``error``

Each library is its own component instance so the operator UI
can pinpoint which mount is filling up.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

_BYTES_PER_GB = 1024**3


@dataclass
class DiskSpaceHealthCheck:
    """One probe per library path. ``free_bytes_provider`` is
    injected so tests can simulate "almost full" without
    actually filling a real volume."""

    component_id: str
    path: Path
    min_free_gb: int
    category: ComponentCategory = ComponentCategory.DISK
    free_bytes_provider: Callable[[Path], int] | None = None

    async def run(self) -> HealthCheckResult:
        free_bytes = self._free_bytes()
        free_gb = free_bytes / _BYTES_PER_GB
        warning_threshold_gb = self.min_free_gb * 1.5
        if free_gb < self.min_free_gb:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=(
                    f"{free_gb:.1f} GB free (< {self.min_free_gb} GB threshold)"
                ),
            )
        if free_gb < warning_threshold_gb:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.WARNING,
                message=(
                    f"{free_gb:.1f} GB free "
                    f"(< {warning_threshold_gb:.1f} GB warning threshold)"
                ),
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=f"{free_gb:.1f} GB free",
        )

    def _free_bytes(self) -> int:
        if self.free_bytes_provider is not None:
            return self.free_bytes_provider(self.path)
        return shutil.disk_usage(self.path).free


__all__ = ["DiskSpaceHealthCheck"]
