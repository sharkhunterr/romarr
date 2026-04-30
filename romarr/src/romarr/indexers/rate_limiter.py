"""Per-indexer monotonic-clock rate limiter (Phase 5).

A single ``RateLimiter`` instance enforces a minimum gap between
``acquire()`` calls. The clock source is :func:`time.monotonic` so a
wall-clock jump backward (NTP correction, manual ``date -s``) cannot
let an indexer exceed its quota — the constitutional FR-009.

Per-indexer isolation: the registry caches one limiter per indexer
id; calls to indexer A's limiter never affect indexer B's gap.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

# Module-level monotonic-clock alias so tests can patch it.
_MONOTONIC: Callable[[], float] = time.monotonic


class RateLimiter:
    """Async limiter with a minimum-gap guarantee.

    Construction: ``RateLimiter(seconds=5)`` allows one acquire every
    5 s. ``seconds=0`` makes ``acquire()`` a no-op so callers don't
    need to special-case "no rate limit".

    Concurrency: the internal :class:`asyncio.Lock` serializes
    concurrent acquirers so the gap calculation stays consistent.
    """

    def __init__(
        self,
        *,
        seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        self._seconds = float(seconds)
        self._clock = clock or _MONOTONIC
        self._last: float | None = None
        self._lock = asyncio.Lock()

    @property
    def seconds(self) -> float:
        return self._seconds

    async def acquire(self) -> float:
        """Block until the minimum gap has elapsed since the last call.

        Returns the number of seconds the caller was delayed (0.0 when
        no delay was needed). Tests use the return value to assert the
        gap was honoured without burning real wall clock.
        """
        if self._seconds == 0:
            return 0.0
        async with self._lock:
            now = self._clock()
            if self._last is None:
                self._last = now
                return 0.0
            elapsed = now - self._last
            wait_for = self._seconds - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
                # Re-read the clock after sleeping so the next gap
                # is measured from when the call actually fired.
                self._last = self._clock()
                return wait_for
            self._last = now
            return 0.0


__all__ = ["RateLimiter"]
