"""Per-indexer rate limiter tests (T036-T039)."""

from __future__ import annotations

import asyncio

import pytest

from romarr.indexers import RateLimiter


@pytest.mark.asyncio
async def test_minimum_gap_enforced() -> None:
    """T036: with seconds=5 (substituted by 0.05 here for test speed),
    the second acquire must be delayed roughly the gap."""
    limiter = RateLimiter(seconds=0.05)
    await limiter.acquire()  # primes the clock; returns 0.0
    delay = await limiter.acquire()
    # The actual sleep is at most one gap; allow a small slack.
    assert delay >= 0.04
    assert delay <= 0.10


@pytest.mark.asyncio
async def test_no_delay_when_zero() -> None:
    """T037: seconds=0 makes acquire a no-op; no clock burn."""
    limiter = RateLimiter(seconds=0)
    for _ in range(10):
        delay = await limiter.acquire()
        assert delay == 0.0


@pytest.mark.asyncio
async def test_monotonic_clock_used() -> None:
    """T038: the limiter uses an injected clock; we inject one whose
    backward jump cannot let the second call escape the gap."""
    clock_value = [100.0]
    limiter = RateLimiter(seconds=0.05, clock=lambda: clock_value[0])
    await limiter.acquire()  # records clock at 100.0
    # Simulate a wall-clock jump backward (NTP correction).
    clock_value[0] = 50.0
    delay = await limiter.acquire()
    # Even with the backward jump the limiter still waits for the gap.
    assert delay > 0


@pytest.mark.asyncio
async def test_per_indexer_isolation() -> None:
    """T039: two RateLimiter instances don't share state."""
    a = RateLimiter(seconds=10.0)
    b = RateLimiter(seconds=10.0)
    # Acquiring on A doesn't queue B's call.
    await a.acquire()
    delay_b = await b.acquire()
    assert delay_b == 0.0


def test_rejects_negative_seconds() -> None:
    with pytest.raises(ValueError):
        RateLimiter(seconds=-1)


@pytest.mark.asyncio
async def test_concurrent_acquires_serialized() -> None:
    """Two concurrent acquires on the same limiter both honour the gap.

    With seconds=0.05 and two concurrent callers, the second must
    wait at least one gap period before completing.
    """
    limiter = RateLimiter(seconds=0.05)
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    await asyncio.gather(limiter.acquire(), limiter.acquire())
    elapsed = loop.time() - t0
    assert elapsed >= 0.04
