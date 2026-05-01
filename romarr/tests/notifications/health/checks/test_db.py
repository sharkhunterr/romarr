"""DB health check (T047)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from romarr.notifications.health.checks.db import DbHealthCheck
from romarr.notifications.types import HealthStatus


def _fast_session_factory() -> Any:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()

    async def factory() -> Any:
        return session

    return factory


def _slow_session_factory(delay_seconds: float) -> Any:
    """Session whose ``execute`` sleeps for ``delay_seconds``."""
    import asyncio

    session = AsyncMock()

    async def slow_execute(*_args: Any, **_kwargs: Any) -> Any:
        await asyncio.sleep(delay_seconds)

    session.execute = slow_execute
    session.close = AsyncMock()

    async def factory() -> Any:
        return session

    return factory


@pytest.mark.asyncio
async def test_fast_round_trip_is_ok() -> None:
    check = DbHealthCheck(session_factory=_fast_session_factory())
    result = await check.run()
    assert result.status is HealthStatus.OK
    assert "DB round-trip" in (result.message or "")


@pytest.mark.asyncio
async def test_slow_round_trip_is_warning() -> None:
    """A round-trip exceeding the warning threshold (default 1s
    — we lower to 0.05s for the test) lands as warning."""
    check = DbHealthCheck(
        session_factory=_slow_session_factory(0.10),
        warning_threshold_seconds=0.05,
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert "slow" in (result.message or "")


@pytest.mark.asyncio
async def test_query_failure_propagates_for_runner_to_handle() -> None:
    """The check itself doesn't catch — the engine's
    ``run_check`` wrapper turns exceptions into
    ``HealthStatus.ERROR`` results. We just verify the
    exception leaves the check's ``run`` so the wrapper sees
    it."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
    session.close = AsyncMock()

    async def factory() -> Any:
        return session

    check = DbHealthCheck(session_factory=factory)
    with pytest.raises(RuntimeError):
        await check.run()
