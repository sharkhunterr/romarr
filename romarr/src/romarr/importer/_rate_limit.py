"""Sliding-window per-key rate limiter (FR-002).

The webhook endpoint accepts at most 10 requests per source IP
per 60-second window. We use a deque of timestamps per key and
expire entries older than the window on every check.

The limiter is **in-process**: multi-worker deployments would
miss cross-worker hits, but the threat model (operator's own
qBittorrent on the operator's own network) doesn't justify a
shared store. If that changes, swap the dict for Redis ZSET.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, timedelta


@dataclass
class SlidingWindowLimiter:
    """Per-key sliding-window counter.

    ``allow(key=..., now=...)`` returns ``True`` when the request
    falls within the budget and ``False`` otherwise; the timestamp
    is recorded on accept so the next call sees one more entry in
    the window.

    ``now`` is injected so tests don't need freezegun.
    """

    window: timedelta
    max_events: int
    _events: dict[str, deque[datetime]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def allow(self, *, key: str, now: datetime) -> bool:
        bucket = self._events[key]
        cutoff = now - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_events:
            return False
        bucket.append(now)
        return True


__all__ = ["SlidingWindowLimiter"]
