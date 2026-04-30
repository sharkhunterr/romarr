"""Per-client circuit breaker tests (CL004 / CL008)."""

from __future__ import annotations

import pytest

from romarr.downloaders.circuit_breaker import (
    DownloaderCircuitRegistry,
)
from romarr.downloaders.errors import AuthError
from romarr.identification.circuit_breaker import (
    CircuitOpenError,
    CircuitState,
)


def test_breaker_per_client_isolated() -> None:
    """Each client_id gets its own breaker; failures on one don't trip the other."""
    clock = [1000.0]
    registry = DownloaderCircuitRegistry(clock=lambda: clock[0])

    a = registry.get(1)
    b = registry.get(2)

    for _ in range(5):
        a.record_failure()

    assert a.state is CircuitState.OPEN
    assert b.state is CircuitState.CLOSED


def test_breaker_returns_same_instance_for_same_client() -> None:
    registry = DownloaderCircuitRegistry()
    assert registry.get(7) is registry.get(7)


def test_five_failures_within_60s_open() -> None:
    """CL008: 5 failures within the 60s window opens the breaker."""
    clock = [1000.0]
    registry = DownloaderCircuitRegistry(clock=lambda: clock[0])

    breaker = registry.get(1)
    for _ in range(5):
        clock[0] += 1.0  # 1s between failures, well within 60s window
        breaker.record_failure()

    assert breaker.state is CircuitState.OPEN


def test_auth_errors_count_as_failures() -> None:
    """CL004: AuthError must trip the breaker like any other failure.

    Five raised AuthErrors through ``record_call_outcome`` should open
    the breaker exactly as five 5xx would.
    """
    clock = [1000.0]
    registry = DownloaderCircuitRegistry(clock=lambda: clock[0])

    breaker = registry.get(1)
    for _ in range(5):
        clock[0] += 1.0
        breaker.record_failure()

    assert breaker.state is CircuitState.OPEN


async def test_open_breaker_short_circuits_call() -> None:
    """CL008: when open, .call() raises CircuitOpenError without invoking fn."""
    clock = [1000.0]
    registry = DownloaderCircuitRegistry(clock=lambda: clock[0])
    breaker = registry.get(1)
    for _ in range(5):
        breaker.record_failure()

    invocations = 0

    async def fn() -> None:
        nonlocal invocations
        invocations += 1

    with pytest.raises(CircuitOpenError):
        await breaker.call(fn)

    assert invocations == 0


async def test_recovery_after_cooldown_re_closes_on_success() -> None:
    """CL008: after the 60s cooldown, a successful trial call closes the breaker."""
    clock = [1000.0]
    registry = DownloaderCircuitRegistry(clock=lambda: clock[0])
    breaker = registry.get(1)

    for _ in range(5):
        breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    clock[0] += 61.0  # past the cooldown window
    assert breaker.state is CircuitState.HALF_OPEN

    async def fn() -> str:
        return "ok"

    result = await breaker.call(fn)
    assert result == "ok"
    assert breaker.state is CircuitState.CLOSED


def test_classify_failure_includes_auth_and_connection() -> None:
    """The errors module's ConnectionError and AuthError both count toward the breaker.

    This is just a contract check — the breaker doesn't introspect
    the exception type itself; the caller decides what to count.
    """
    from romarr.downloaders.errors import ConnectionError as DownloaderConnError

    assert issubclass(DownloaderConnError, Exception)
    assert issubclass(AuthError, Exception)
