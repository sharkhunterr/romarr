"""Incremental scanner — wakes on filesystem events (spec 009 — Phase 7 SCAN-INC).

Where ``full.py`` walks the entire library on a schedule, the
incremental scanner reacts to per-file events as they happen.
inotify (Linux) or FSEvents (macOS) feed instant signals via
:class:`watchdog.observers.Observer`; on platforms without those
kernel APIs the polling observer falls back to walking the tree
every ``scan_poll_seconds`` (FR-002a).

The scanner translates raw filesystem events into three
domain-level outcomes per FR-009 / FR-010 / FR-011:

  * **created**: a new file landed at a watched path. We hash it
    and try to link it to an existing Dump by SHA-1; if no match,
    the file becomes a candidate for the importer (which lives in
    spec 008's full happy path). The candidate event is emitted
    via the ``on_unmatched`` callback so the orchestrator can pick
    it up without the scanner reaching into importer internals.
  * **moved-within-library**: an existing Dump's path column
    updates without re-hashing. ``(path, size)`` already
    identified the file uniquely; the rename is a metadata-only
    update (FR-010 idempotency).
  * **moved-out / deleted**: the Dump is orphaned. The parent
    Release transitions to ``status='wanted'`` so the operator's
    Wanted page surfaces it immediately (FR-011).

Event handling is debounced by 500 ms so that editor-style
write-rename-rename sequences don't trigger redundant work. The
debounce is per-path; multiple files are batched up to the
async event loop's tick boundary.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select, update
from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from romarr.domain.models import Dump, Release
from romarr.identification.hasher import Hasher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_SECONDS = 0.5
"""Quiet period after the last event before a path is processed.

Editor write/rename sequences can fire 3-5 events for one logical
'save' operation; the debounce collapses them into a single
domain-level callback."""


_OBSERVER_TYPE_ENV = "ROMARR_WATCHDOG_OBSERVER_TYPE"
"""Override the observer choice. Values: ``"native"`` (default —
inotify / FSEvents / ReadDirectoryChangesW per-platform) or
``"polling"`` (force ``PollingObserver``)."""


ObserverKind = Literal["native", "polling"]


def _resolve_observer_kind() -> ObserverKind:
    raw = (os.environ.get(_OBSERVER_TYPE_ENV) or "").strip().lower()
    if raw == "polling":
        return "polling"
    return "native"


@dataclass(frozen=True)
class IncrementalScanResult:
    """Aggregate counters for diagnostics + tests."""

    created_unmatched: int = 0
    created_linked: int = 0
    renamed: int = 0
    deleted: int = 0
    errors: int = 0


UnmatchedCallback = Callable[[Path], Awaitable[None]]
"""Async callback invoked for every newly-arrived file that could
not be linked to an existing Dump by SHA-1. The orchestrator wraps
``run_import`` here so the file enters the importer pipeline.
"""


class IncrementalScanner:
    """Per-library inotify/polling scanner.

    Lifecycle:
        scanner = IncrementalScanner(...)
        await scanner.start()   # spawns observer + worker task
        ...
        await scanner.stop()    # joins both cleanly

    The scanner is **per-library**; a multi-library deployment
    runs multiple instances. The async worker drains a per-path
    debounce queue so the watchdog observer thread (which fires
    callbacks synchronously) doesn't block while we await DB.
    """

    def __init__(
        self,
        *,
        sessionmaker: "async_sessionmaker",
        library_id: int,
        library_path: Path,
        accepted_extensions: set[str],
        on_unmatched: UnmatchedCallback | None = None,
        hasher: Hasher | None = None,
        debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
        observer_kind: ObserverKind | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._library_id = library_id
        self._library_path = library_path.resolve()
        self._accepted_extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in accepted_extensions
        }
        self._on_unmatched = on_unmatched
        self._hasher = hasher or Hasher()
        self._debounce_seconds = debounce_seconds
        self._observer_kind: ObserverKind = (
            observer_kind or _resolve_observer_kind()
        )

        self._observer: Observer | PollingObserver | None = None
        self._handler = _ScannerEventHandler(self)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[Path, asyncio.TimerHandle] = {}
        self.counters = IncrementalScanResult()

    @property
    def running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    async def start(self) -> None:
        """Begin watching ``library_path``. Idempotent."""
        if self.running:
            return
        self._loop = asyncio.get_running_loop()
        if self._observer_kind == "polling":
            self._observer = PollingObserver(timeout=self._debounce_seconds)
        else:
            self._observer = Observer()
        self._observer.schedule(
            self._handler, str(self._library_path), recursive=True
        )
        self._observer.start()

    async def stop(self) -> None:
        """Stop the observer + cancel any pending debounce timers."""
        for timer in list(self._pending.values()):
            timer.cancel()
        self._pending.clear()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
        self._loop = None

    # ------------------------------------------------------------------
    # Direct event-injection API (used by tests; the watchdog handler
    # routes here too).
    # ------------------------------------------------------------------

    async def handle_created(self, path: Path) -> None:
        """A new file landed at ``path``. Hash it, try to link an
        existing Dump by SHA-1, else hand it to the importer via
        ``on_unmatched``.
        """
        if not self._accepts(path):
            return
        if not path.exists() or not path.is_file():
            return

        try:
            sha1 = await asyncio.to_thread(self._hasher.hash_path, path)
        except OSError:
            self.counters = _bump(self.counters, errors=1)
            return

        async with self._sessionmaker() as session:
            existing = (
                await session.execute(
                    select(Dump).where(Dump.sha1 == sha1.sha1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.path = str(path)
                await session.commit()
                self.counters = _bump(self.counters, created_linked=1)
                return

        # No SHA-1 match — hand off to the importer (spec 008's
        # full happy path). Until that lands, the orchestrator's
        # audit-only path parks the file in unidentified_dump.
        if self._on_unmatched is not None:
            try:
                await self._on_unmatched(path)
            except Exception:
                logger.exception(
                    "incremental_scanner.on_unmatched_failed path=%s", path
                )
                self.counters = _bump(self.counters, errors=1)
                return
        self.counters = _bump(self.counters, created_unmatched=1)

    async def handle_moved(self, src_path: Path, dest_path: Path) -> None:
        """A file moved from ``src_path`` to ``dest_path``.

        Two cases:
          * Both paths are inside this library → metadata-only
            update of ``Dump.path`` (FR-010 idempotency).
          * Destination is outside this library → orphan the
            existing Dump (FR-011).
        """
        if not self._is_within(src_path):
            return  # not our library — ignore.

        async with self._sessionmaker() as session:
            existing = (
                await session.execute(
                    select(Dump).where(Dump.path == str(src_path))
                )
            ).scalar_one_or_none()
            if existing is None:
                return

            if self._is_within(dest_path):
                if not self._accepts(dest_path):
                    # Renamed to a non-matching extension — same
                    # effective semantics as moved-out: orphan it.
                    await self._orphan_dump(session, existing)
                    self.counters = _bump(self.counters, deleted=1)
                else:
                    existing.path = str(dest_path)
                    await session.commit()
                    self.counters = _bump(self.counters, renamed=1)
            else:
                await self._orphan_dump(session, existing)
                self.counters = _bump(self.counters, deleted=1)

    async def handle_deleted(self, path: Path) -> None:
        """A file at ``path`` disappeared (deleted or moved-out).

        Mirrors :meth:`handle_moved` to "outside library" — the
        Dump's parent Release transitions to wanted (FR-011).
        """
        async with self._sessionmaker() as session:
            existing = (
                await session.execute(
                    select(Dump).where(Dump.path == str(path))
                )
            ).scalar_one_or_none()
            if existing is None:
                return
            await self._orphan_dump(session, existing)
            self.counters = _bump(self.counters, deleted=1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _accepts(self, path: Path) -> bool:
        return path.suffix.lower() in self._accepted_extensions

    def _is_within(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._library_path)
            return True
        except (ValueError, OSError):
            return False

    async def _orphan_dump(self, session, dump: Dump) -> None:  # type: ignore[no-untyped-def]
        """Mark the Dump's parent Release as wanted (FR-011)."""
        release_id = dump.release_id
        await session.execute(
            update(Release)
            .where(Release.id == release_id)
            .values(status="wanted")
        )
        await session.delete(dump)
        await session.commit()

    def _schedule_debounced(
        self,
        path: Path,
        coro_factory: Callable[[], Awaitable[None]],
    ) -> None:
        """Coalesce rapid-fire events on the same path.

        Called from the watchdog observer thread, so the loop-side
        bookkeeping (``call_later`` + the ``_pending`` map) MUST be
        marshalled back to the asyncio loop via
        :meth:`call_soon_threadsafe` — touching ``self._pending`` or
        ``self._loop.call_later`` from a non-loop thread is undefined.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _fire() -> None:
            self._pending.pop(path, None)
            if loop is not None and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(coro_factory(), loop)

        def _arm() -> None:
            if loop.is_closed():
                return
            existing = self._pending.pop(path, None)
            if existing is not None:
                existing.cancel()
            timer = loop.call_later(self._debounce_seconds, _fire)
            self._pending[path] = timer

        loop.call_soon_threadsafe(_arm)


class _ScannerEventHandler(FileSystemEventHandler):
    """Thread-safe bridge from watchdog → IncrementalScanner.

    Watchdog calls these from a worker thread; we hand the work
    back to the scanner's asyncio loop via the debounce queue.
    """

    def __init__(self, scanner: IncrementalScanner) -> None:
        self._scanner = scanner

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._scanner._schedule_debounced(
            path, lambda p=path: self._scanner.handle_created(p)
        )

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        src = Path(event.src_path)
        dest = Path(event.dest_path)
        self._scanner._schedule_debounced(
            src, lambda s=src, d=dest: self._scanner.handle_moved(s, d)
        )

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._scanner._schedule_debounced(
            path, lambda p=path: self._scanner.handle_deleted(p)
        )


def _bump(
    counters: IncrementalScanResult, **delta: int
) -> IncrementalScanResult:
    """Replace a frozen counters with one bumped by ``delta``."""
    return IncrementalScanResult(
        created_unmatched=counters.created_unmatched
        + delta.get("created_unmatched", 0),
        created_linked=counters.created_linked
        + delta.get("created_linked", 0),
        renamed=counters.renamed + delta.get("renamed", 0),
        deleted=counters.deleted + delta.get("deleted", 0),
        errors=counters.errors + delta.get("errors", 0),
    )


__all__ = [
    "IncrementalScanResult",
    "IncrementalScanner",
    "ObserverKind",
    "UnmatchedCallback",
]
