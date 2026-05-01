"""Library path health check (T049)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from romarr.notifications.health.checks.library_path import (
    LibraryPathHealthCheck,
)
from romarr.notifications.types import HealthStatus


@pytest.mark.asyncio
async def test_existing_path_is_ok(tmp_path: Path) -> None:
    check = LibraryPathHealthCheck(
        component_id="library:Cartridges", path=tmp_path
    )
    result = await check.run()
    assert result.status is HealthStatus.OK


@pytest.mark.asyncio
async def test_missing_path_is_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    check = LibraryPathHealthCheck(
        component_id="library:gone", path=missing
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    # The structured message carries the OS exception class so
    # the operator can distinguish ENOENT from EACCES at a glance.
    assert "FileNotFoundError" in (result.message or "")


@pytest.mark.asyncio
async def test_stat_timeout_is_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T049: a stat that takes longer than the configured
    timeout surfaces as ``error`` with reason ``timeout``."""

    async def slow_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.20)
        return fn(*args, **kwargs)

    monkeypatch.setattr(
        "romarr.notifications.health.checks.library_path.asyncio.to_thread",
        slow_to_thread,
    )
    check = LibraryPathHealthCheck(
        component_id="library:Cartridges",
        path=tmp_path,
        timeout_seconds=0.05,
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert "timeout" in (result.message or "")
