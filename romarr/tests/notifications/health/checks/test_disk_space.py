"""Disk space check (T046, FR-020)."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.notifications.health.checks.disk_space import (
    DiskSpaceHealthCheck,
)
from romarr.notifications.types import HealthStatus

_BYTES_PER_GB = 1024**3


def _free_bytes_provider(free_gb: float):
    """Return a callable that always reports ``free_gb`` GB
    free, regardless of the path passed in."""

    def provider(_path: Path) -> int:
        return int(free_gb * _BYTES_PER_GB)

    return provider


@pytest.mark.asyncio
async def test_free_space_at_1_2x_threshold_emits_warning() -> None:
    """T046: ``free = min x 1.2`` falls in the
    [min, min x 1.5) warning band."""
    check = DiskSpaceHealthCheck(
        component_id="library:Cartridges",
        path=Path("/library"),
        min_free_gb=10,
        free_bytes_provider=_free_bytes_provider(12.0),
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING


@pytest.mark.asyncio
async def test_free_space_at_0_5x_threshold_emits_error() -> None:
    """T046: ``free = min x 0.5`` is below threshold ⇒ error."""
    check = DiskSpaceHealthCheck(
        component_id="library:Cartridges",
        path=Path("/library"),
        min_free_gb=10,
        free_bytes_provider=_free_bytes_provider(5.0),
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR


@pytest.mark.asyncio
async def test_free_space_at_2x_threshold_is_ok() -> None:
    check = DiskSpaceHealthCheck(
        component_id="library:Cartridges",
        path=Path("/library"),
        min_free_gb=10,
        free_bytes_provider=_free_bytes_provider(20.0),
    )
    result = await check.run()
    assert result.status is HealthStatus.OK


@pytest.mark.asyncio
async def test_free_space_at_min_exactly_is_warning() -> None:
    """Boundary: ``free == min`` is the ok/warning boundary —
    we treat ``free < min`` as error, so equal is warning."""
    check = DiskSpaceHealthCheck(
        component_id="library:Cartridges",
        path=Path("/library"),
        min_free_gb=10,
        free_bytes_provider=_free_bytes_provider(10.0),
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
