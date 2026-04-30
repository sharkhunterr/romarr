"""Library scanner (spec 009 — Phases 6-7).

Two scanners ship in spec 009:

  * **Full scan** (this slice) — walks ``library.path`` and
    discovers / re-binds / orphans Dump rows.
  * **Incremental scan** (next slice) — inotify-driven via
    :mod:`watchdog`, with a polling fallback for storage that
    doesn't propagate kernel events.

Both feed the same :class:`ScanProgressEvent` channel so the
WebSocket consumer renders a single progress bar regardless of
which scanner produced the event.
"""

from romarr.libraries.scanner.full import (
    FullScanResult,
    full_scan,
    walk_library,
)
from romarr.libraries.scanner.progress import (
    ScanProgressEmitter,
    ScanProgressEvent,
)

__all__ = [
    "FullScanResult",
    "ScanProgressEmitter",
    "ScanProgressEvent",
    "full_scan",
    "walk_library",
]
