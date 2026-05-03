"""Metadata-cache size health check (spec 002 CL008, FR-016a).

The ``metadata_cache`` table is bounded by the unique
constraint on ``(provider_name, provider_game_id)`` — one row
per provider/game. There's no LRU eviction; entries leave only
when their ``expires_at`` lapses or the providing Game is
deleted (CASCADE). For an active library that's typically a
few MB, but a misconfigured TTL or a pathological library
import can grow the table without bound.

This check warns at 2 GB on disk and errors at 4 GB so the
operator notices before the SQLite file becomes a backup
liability. The size estimate is the raw row count multiplied by
an empirical bytes-per-row figure — exact byte counting via
``dbstat`` is portable to SQLite + Postgres but adds a SELECT
that scans the whole table; the estimate is good enough to
trigger the alert window.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from romarr.metadata.models import MetadataCache
from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_BYTES_PER_GB = 1024**3

# Empirical: a typical IGDB+ScreenScraper joined payload weighs
# ~2 KB after JSON serialisation. We bias slightly high so the
# warning fires before the row-count estimate can lie.
_BYTES_PER_ROW_ESTIMATE = 2_500

WARNING_THRESHOLD_GB = 2
ERROR_THRESHOLD_GB = 4


SessionFactory = Callable[[], Awaitable["AsyncSession"]]


@dataclass
class MetadataCacheSizeHealthCheck:
    """Estimate ``metadata_cache`` size and surface a warning
    when it crosses the configured threshold (FR-016a).

    The session factory is injected so tests can hand in an
    in-memory SQLite session without spinning up the lifespan
    plumbing. ``bytes_per_row`` is also injectable so a future
    SQL-level ``pragma page_count`` integration can replace the
    estimate without breaking the public surface.
    """

    component_id: str = "metadata.cache"
    category: ComponentCategory = ComponentCategory.METADATA
    session_factory: SessionFactory | None = None
    warning_threshold_gb: float = float(WARNING_THRESHOLD_GB)
    error_threshold_gb: float = float(ERROR_THRESHOLD_GB)
    bytes_per_row: int = _BYTES_PER_ROW_ESTIMATE

    async def run(self) -> HealthCheckResult:
        if self.session_factory is None:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.WARNING,
                message="no session factory wired",
            )

        async with await self.session_factory() as session:
            row_count = (
                await session.execute(
                    select(func.count(MetadataCache.id))
                )
            ).scalar_one()

        size_gb = (row_count * self.bytes_per_row) / _BYTES_PER_GB

        if size_gb >= self.error_threshold_gb:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=(
                    f"metadata_cache estimated at {size_gb:.2f} GB "
                    f"(>= {self.error_threshold_gb:.0f} GB threshold)"
                ),
            )
        if size_gb >= self.warning_threshold_gb:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.WARNING,
                message=(
                    f"metadata_cache estimated at {size_gb:.2f} GB "
                    f"(>= {self.warning_threshold_gb:.0f} GB threshold)"
                ),
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=(
                f"metadata_cache estimated at {size_gb:.2f} GB "
                f"({row_count} rows)"
            ),
        )


__all__ = [
    "ERROR_THRESHOLD_GB",
    "MetadataCacheSizeHealthCheck",
    "WARNING_THRESHOLD_GB",
]
