"""Circuit breaker unit tests — FR-027."""

from __future__ import annotations

import pytest

from romarr.identification.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class _ManualClock:
    """Deterministic monotonic clock for the tests."""

    def __init__(self, t: float = 0.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def test_breaker_starts_closed() -> None:
    cb = CircuitBreaker("svc")
    assert cb.state == CircuitState.CLOSED


def test_breaker_opens_after_5_failures_in_window() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc", failure_threshold=5, window_seconds=60, clock=clock
    )
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()  # 5th
    assert cb.state == CircuitState.OPEN


def test_breaker_does_not_open_when_failures_outside_window() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc", failure_threshold=5, window_seconds=60, clock=clock
    )
    for _ in range(4):
        cb.record_failure()
    clock.advance(70)  # window slid past
    cb.record_failure()  # only 1 fresh failure
    assert cb.state == CircuitState.CLOSED


def test_breaker_half_opens_after_cooldown() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc",
        failure_threshold=2,
        window_seconds=60,
        cooldown_seconds=30,
        clock=clock,
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    clock.advance(31)
    assert cb.state == CircuitState.HALF_OPEN


def test_breaker_closes_on_half_open_success() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc",
        failure_threshold=2,
        window_seconds=60,
        cooldown_seconds=10,
        clock=clock,
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(11)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_breaker_reopens_on_half_open_failure() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc",
        failure_threshold=2,
        window_seconds=60,
        cooldown_seconds=10,
        clock=clock,
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(11)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    # Re-opened; cooldown restarted from this moment.
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_breaker_call_short_circuits_when_open() -> None:
    clock = _ManualClock()
    cb = CircuitBreaker(
        "svc", failure_threshold=2, window_seconds=60, clock=clock
    )
    cb.record_failure()
    cb.record_failure()

    async def boom() -> str:  # pragma: no cover — should never run
        raise RuntimeError("breaker should have short-circuited")

    with pytest.raises(CircuitOpenError):
        await cb.call(boom)


@pytest.mark.asyncio
async def test_breaker_call_records_success_and_failure() -> None:
    cb = CircuitBreaker("svc")

    async def ok() -> str:
        return "fine"

    async def bad() -> str:
        raise RuntimeError("nope")

    assert await cb.call(ok) == "fine"

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await cb.call(bad)

    assert cb.state == CircuitState.OPEN


def test_breaker_rejects_invalid_args() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker("svc", failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker("svc", window_seconds=0)
    with pytest.raises(ValueError):
        CircuitBreaker("svc", cooldown_seconds=-1)
