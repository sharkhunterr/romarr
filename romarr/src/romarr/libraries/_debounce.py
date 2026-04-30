"""Generic per-key debounce primitive.

Used by:

  * the heartbeat loop (FR-029) to avoid emitting duplicate
    ``OnHealthIssue`` / recovery events when a library flaps; and
  * spec 011's notification consumer to coalesce repeat exporter
    failures into a single ``OnHealthIssue`` per 5-minute window.

The primitive is pure: it doesn't sleep, doesn't read a clock —
the caller threads ``now`` in. That keeps the unit tests
deterministic without freezegun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class WindowedDebouncer[K]:
    """Per-key debounce — the same key can emit at most once per
    ``window``.

    Usage:
        deb = WindowedDebouncer[tuple[int, LibraryStatus]](window=timedelta(minutes=5))
        if deb.should_emit(key=("lib-1", "unavailable"), now=now):
            emit_event(...)

    The state is in-process only. A process restart resets every
    cooldown — that's fine for both consumers (a process restart is
    itself a reportable event).
    """

    window: timedelta
    _last_emit_at: dict[K, datetime] = field(default_factory=dict)

    def should_emit(self, *, key: K, now: datetime) -> bool:
        """Return True iff the key has not emitted within
        ``window``. Records the emission timestamp on True so the
        next call within the window returns False."""
        last = self._last_emit_at.get(key)
        if last is not None and now - last < self.window:
            return False
        self._last_emit_at[key] = now
        return True

    def reset(self, *, key: K) -> None:
        """Forget the last-emit timestamp for ``key``. Used by the
        heartbeat loop when a library is deleted from the registry —
        a future re-creation with the same id would otherwise inherit
        the suppression window."""
        self._last_emit_at.pop(key, None)


__all__ = ["WindowedDebouncer"]
