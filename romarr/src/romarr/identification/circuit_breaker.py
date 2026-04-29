"""Generic circuit breaker for remote-service guards.

Used by the hash-match cascade (FR-027) and reused by later specs
(metadata providers in 002, indexers in 004, download clients in 005).
The pattern is identical everywhere: 5 failures within a 60-second
window opens the circuit; the breaker enters half-open after a 60s
cooldown and allows exactly one trial call.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised by :class:`CircuitBreaker` when a call is short-circuited."""

    def __init__(self, breaker_name: str) -> None:
        super().__init__(f"circuit breaker {breaker_name!r} is open")
        self.breaker_name = breaker_name


class CircuitBreaker:
    """A simple monotonic-clock circuit breaker.

    Defaults match FR-027 / FR-027a from spec 001 and the matching
    rules in specs 002 / 004 / 005:
      - 5 failures within a 60-second window → CLOSED → OPEN
      - 60 seconds without failures → OPEN → HALF_OPEN
      - one success in HALF_OPEN → CLOSED
      - one failure in HALF_OPEN → OPEN (cooldown restarts)
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")

        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_times: deque[float] = deque()
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Current state, recomputed lazily — opens self-heal on read."""
        self._maybe_transition_to_half_open()
        return self._state

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and self._clock() - self._opened_at >= self.cooldown_seconds
        ):
            self._state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        """Record a successful call.

        From HALF_OPEN we close the breaker. From CLOSED this is a
        no-op for state purposes; we don't bother clearing the failure
        deque because the sliding window naturally times them out.
        """
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_times.clear()
            self._opened_at = None

    def record_failure(self) -> None:
        """Record a failure. May open or re-open the breaker."""
        now = self._clock()

        if self._state == CircuitState.HALF_OPEN:
            # A trial call failed → re-open and restart the cooldown.
            self._state = CircuitState.OPEN
            self._opened_at = now
            return

        # Trim failures outside the window.
        cutoff = now - self.window_seconds
        while self._failure_times and self._failure_times[0] < cutoff:
            self._failure_times.popleft()
        self._failure_times.append(now)

        if (
            self._state == CircuitState.CLOSED
            and len(self._failure_times) >= self.failure_threshold
        ):
            self._state = CircuitState.OPEN
            self._opened_at = now

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Invoke an async callable through the breaker.

        Raises :class:`CircuitOpenError` synchronously when the circuit
        is OPEN (no network round-trip). Otherwise runs ``fn()`` and
        records the outcome.
        """
        # Refresh state in case the cooldown elapsed.
        self._maybe_transition_to_half_open()

        if self._state == CircuitState.OPEN:
            raise CircuitOpenError(self.name)

        try:
            result = await fn()
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result
