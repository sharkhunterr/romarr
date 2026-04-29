"""Per-IP rate limiter for the auth-attempt endpoints — FR-010a.

10 attempts per minute per source IP across:
  - ``POST /api/v3/auth/login``
  - ``POST /api/v3/auth/setup``
  - ``GET  /auth/oidc/callback``

Both successful and failed attempts count toward the bucket so an
attacker can't mix them to bypass. When the limit is hit:
  - The endpoint returns HTTP 429 with ``Retry-After`` populated.
  - The bcrypt comparison MUST NOT run (no oracle of hash work).

Implementation: in-memory sliding-window counters. Operators
running multiple Romarr processes (the constitutional model is
single-instance, but k8s deployments may span replicas behind a
load balancer) can swap this for a Redis-backed implementation
without changing the consumer interface.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from romarr.auth.errors import RateLimitedError

DEFAULT_LIMIT: int = 10
"""FR-010a — 10 attempts per window per IP."""

DEFAULT_WINDOW_SECONDS: float = 60.0
"""FR-010a — one-minute sliding window."""


class IpRateLimiter:
    """Sliding-window IP-keyed rate limiter.

    ``check`` raises :class:`RateLimitedError` when an IP would
    exceed the limit. The caller MUST invoke ``check`` BEFORE doing
    any expensive work (bcrypt compare, OIDC code exchange) so the
    short-circuit actually saves work.

    Both successful and failed attempts contribute to the bucket per
    spec 010 FR-010a — call ``record`` after every attempt regardless
    of outcome.
    """

    def __init__(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        # IP → recent-attempt timestamps (oldest first).
        self._buckets: dict[str, deque[float]] = {}

    def check(self, ip_address: str) -> None:
        """Raise :class:`RateLimitedError` when ``ip_address`` is over budget.

        Empty / unknown IPs (e.g., during local tests) bypass — the
        limiter is per-IP only and we don't want to lock out tests
        that don't supply one.
        """
        if not ip_address:
            return

        now = self._clock()
        bucket = self._buckets.get(ip_address)
        if bucket is None:
            return

        # Trim entries outside the window.
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.limit:
            # Retry-After: seconds until the oldest entry rolls off.
            oldest = bucket[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            raise RateLimitedError(retry_after_seconds=retry_after)

    def record(self, ip_address: str) -> None:
        """Append a new attempt timestamp for ``ip_address``."""
        if not ip_address:
            return
        bucket = self._buckets.setdefault(ip_address, deque())
        bucket.append(self._clock())

    def reset(self, ip_address: str | None = None) -> None:
        """Clear counters — for tests or admin overrides.

        Called with no argument it nukes every bucket; called with an
        IP it clears just that one.
        """
        if ip_address is None:
            self._buckets.clear()
        else:
            self._buckets.pop(ip_address, None)
