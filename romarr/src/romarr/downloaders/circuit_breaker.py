"""Per-client circuit breaker registry (CL004).

Article III forbids a duplicated breaker library — every spec layer
that needs a breaker reuses
:class:`romarr.identification.circuit_breaker.CircuitBreaker`. This
module is a thin per-``client_id`` registry on top of that breaker:
calls to ``registry.get(client_id)`` return a stable
:class:`CircuitBreaker` instance scoped to that client, and the
identification module's defaults (5 failures / 60s window /
60s cooldown) match FR-022a's spec verbatim.

Stuck-grab retry consults the breaker before issuing an outbound
call — when ``state == OPEN`` the caller skips the round-trip and
just bumps ``last_attempt_at`` so the retry ledger remains coherent
(spec 005's FR-022a wording).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from romarr.identification.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class DownloaderCircuitRegistry:
    """Lazy registry of per-client breakers.

    The registry never evicts entries — operators rarely have more
    than a handful of clients, so the memory cost of one breaker per
    seen client_id is negligible. Tests inject a deterministic clock
    via the ``clock=`` kwarg.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._clock = clock
        self._failure_threshold = failure_threshold
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._breakers: dict[int, CircuitBreaker] = {}

    def get(self, client_id: int) -> CircuitBreaker:
        """Return the breaker for ``client_id``, creating it on first sight."""
        breaker = self._breakers.get(client_id)
        if breaker is None:
            breaker = CircuitBreaker(
                name=f"download_client:{client_id}",
                failure_threshold=self._failure_threshold,
                window_seconds=self._window_seconds,
                cooldown_seconds=self._cooldown_seconds,
                clock=self._clock,
            )
            self._breakers[client_id] = breaker
        return breaker


__all__ = [
    "CircuitOpenError",
    "CircuitState",
    "DownloaderCircuitRegistry",
]
