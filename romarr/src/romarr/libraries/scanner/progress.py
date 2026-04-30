"""Scan-progress event emitter (FR-012).

A long full-scan must emit progress events every N files so the
WebSocket consumer (spec 011) can drive a per-library progress
bar. The emitter is **pure**: it counts files seen, calls the
sink every N events, never sleeps, never reads a clock — the
caller threads ``now`` in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime


@dataclass(frozen=True)
class ScanProgressEvent:
    """One snapshot of a scan's progress state.

    The WebSocket consumer renders these into a percent-complete
    plus the latest ``note`` text. ``files_seen`` includes files
    that were skipped, processed, orphaned, or failed — every
    iteration of the walker increments it once.
    """

    library_id: int
    scan_kind: str
    files_seen: int
    files_processed: int
    files_skipped: int
    files_orphaned: int
    files_unmatched: int
    started_at: datetime
    last_event_at: datetime
    note: str | None = None


class ScanProgressEmitter:
    """Tracks running counters and dispatches a
    :class:`ScanProgressEvent` to the configured ``sink`` every
    ``every`` files seen.

    Always emits a final event on :meth:`finish`, so the consumer
    sees the terminal state regardless of whether the file count
    is a multiple of ``every``.

    The sink is intentionally synchronous: this is a pub/sub
    notification, not an awaitable workflow. Async forwarding
    happens upstream of this emitter.
    """

    def __init__(
        self,
        *,
        library_id: int,
        scan_kind: str,
        started_at: datetime,
        sink: Callable[[ScanProgressEvent], None] | None = None,
        every: int = 100,
    ) -> None:
        if every <= 0:
            raise ValueError("every must be positive")
        self._library_id = library_id
        self._scan_kind = scan_kind
        self._started_at = started_at
        self._sink = sink
        self._every = every
        self.files_seen = 0
        self.files_processed = 0
        self.files_skipped = 0
        self.files_orphaned = 0
        self.files_unmatched = 0

    # ------------------------------------------------------------------
    # Counter mutation. Each call records the running totals; the
    # caller decides which counter applies to the current file.

    def record_skipped(self, *, now: datetime) -> None:
        self.files_seen += 1
        self.files_skipped += 1
        self._maybe_emit(now=now)

    def record_processed(self, *, now: datetime) -> None:
        self.files_seen += 1
        self.files_processed += 1
        self._maybe_emit(now=now)

    def record_unmatched(self, *, now: datetime) -> None:
        self.files_seen += 1
        self.files_unmatched += 1
        self._maybe_emit(now=now)

    def record_orphan(self, *, now: datetime) -> None:
        """Orphaned Dump events do NOT increment ``files_seen`` — the
        orphan sweep happens after the walk and operates on a
        different population (existing Dumps, not on-disk files).
        Counted separately so the operator sees both numbers."""
        self.files_orphaned += 1
        self._maybe_emit(now=now, force=True)

    # ------------------------------------------------------------------
    # Emission

    def _maybe_emit(self, *, now: datetime, force: bool = False) -> None:
        if self._sink is None:
            return
        if force or self.files_seen % self._every == 0:
            self._sink(self._snapshot(now=now))

    def finish(self, *, now: datetime, note: str | None = None) -> ScanProgressEvent:
        """Emit and return the terminal snapshot."""
        snapshot = self._snapshot(now=now, note=note)
        if self._sink is not None:
            self._sink(snapshot)
        return snapshot

    def _snapshot(
        self, *, now: datetime, note: str | None = None
    ) -> ScanProgressEvent:
        return ScanProgressEvent(
            library_id=self._library_id,
            scan_kind=self._scan_kind,
            files_seen=self.files_seen,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
            files_orphaned=self.files_orphaned,
            files_unmatched=self.files_unmatched,
            started_at=self._started_at,
            last_event_at=now,
            note=note,
        )


__all__ = ["ScanProgressEmitter", "ScanProgressEvent"]
