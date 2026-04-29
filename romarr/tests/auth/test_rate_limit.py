"""IpRateLimiter tests — FR-010a (10 attempts/min/IP)."""

from __future__ import annotations

import pytest

from romarr.auth import IpRateLimiter, RateLimitedError


class _ManualClock:
    def __init__(self, t: float = 0.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def test_under_limit_passes() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=10, window_seconds=60, clock=clock)
    for _ in range(10):
        limiter.check("1.2.3.4")
        limiter.record("1.2.3.4")
    # 11th attempt within the window → blocked
    with pytest.raises(RateLimitedError) as exc:
        limiter.check("1.2.3.4")
    assert exc.value.retry_after_seconds >= 1


def test_window_slide_allows_new_attempts() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=2, window_seconds=10, clock=clock)
    limiter.record("ip")
    limiter.record("ip")
    with pytest.raises(RateLimitedError):
        limiter.check("ip")
    clock.advance(11)  # entries roll off
    limiter.check("ip")  # passes


def test_per_ip_buckets_independent() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=2, window_seconds=60, clock=clock)
    for _ in range(2):
        limiter.record("a")
    with pytest.raises(RateLimitedError):
        limiter.check("a")
    # Different IP not affected.
    limiter.check("b")


def test_empty_ip_bypasses() -> None:
    """An empty IP (e.g., test client) bypasses the limiter."""
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.record("")
    limiter.check("")  # not raised


def test_reset_clears_specific_ip() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.record("a")
    limiter.record("a")
    with pytest.raises(RateLimitedError):
        limiter.check("a")
    limiter.reset("a")
    limiter.check("a")  # now passes


def test_reset_all_clears_every_ip() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.record("a")
    limiter.record("b")
    limiter.reset()  # nuke
    limiter.check("a")
    limiter.check("b")


def test_invalid_args() -> None:
    with pytest.raises(ValueError):
        IpRateLimiter(limit=0)
    with pytest.raises(ValueError):
        IpRateLimiter(window_seconds=0)


def test_retry_after_seconds_in_error() -> None:
    clock = _ManualClock()
    limiter = IpRateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.record("ip")
    with pytest.raises(RateLimitedError) as exc:
        limiter.check("ip")
    assert 0 < exc.value.retry_after_seconds <= 60
