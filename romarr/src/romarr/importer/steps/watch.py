"""Polling watcher that wakes the orchestrator on completed downloads (FR-001).

The webhook surface (``/api/v3/webhook/download-complete``) is the
operator's primary post-completion signal — qBit / SAB push as soon as
they finish a download. The polling watcher is the **fallback** path
for clients that don't speak webhooks (or for the case where a webhook
was lost in transit). It's a 30-second loop that asks every configured
client what it has and dispatches new (client_id, native_id) pairs to
the orchestrator's ``run_import`` callable.

Design properties (per spec 008 FR-001 / SC-008):

* Polls every ``interval_seconds`` (default 30 s) while running.
* Iterates over every configured client; one client raising does NOT
  abort the tick — the loop logs the failure and continues with the
  remaining clients (FR-019 — fault isolation).
* Skips items that already carry the ``romarr-imported`` tag
  (qBit's ``imported`` flag) AND items the loop has already seen
  this run (in-memory dedup). The dedup set is bounded — old entries
  are dropped on a sliding eviction once the cap is reached.
* On shutdown ``stop()`` cancels the background task cleanly.

The watcher is intentionally I/O-light: no DB writes, no per-tick
allocations beyond the dedup set. The dispatcher callable owns the
import contract (typically the orchestrator's ``run_import``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.downloaders.base import DownloadClient
    from romarr.downloaders.types import ManagedDownload

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30
"""Default poll cadence — matches FR-001's "every 30 s"."""

_DEDUP_CAP = 10_000
"""Hard cap on the in-memory ``seen`` set; evicts oldest on overflow."""


ClientProvider = Callable[[], Awaitable[Sequence["DownloadClient"]]]
"""Async callable returning the current set of enabled clients.

The watcher re-requests the client list on every tick so dynamic
add/remove of clients (via the API) takes effect on the next poll
without restarting the loop.
"""

Dispatcher = Callable[["ManagedDownload"], Awaitable[None]]
"""Async callable invoked once per newly-seen completed download."""


class WatcherLoop:
    """Background polling watcher around a configurable client provider."""

    def __init__(
        self,
        *,
        get_clients: ClientProvider,
        dispatcher: Dispatcher,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._get_clients = get_clients
        self._dispatcher = dispatcher
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._seen: set[tuple[int, str]] = set()
        self._seen_order: list[tuple[int, str]] = []

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Launch the polling loop as a background task. Idempotent."""
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="watcher_loop")

    async def stop(self) -> None:
        """Signal stop, await the task. Safe to call when not running."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def tick(self) -> int:
        """Run one poll cycle. Public for tests + manual triggering.

        Returns the number of items dispatched this tick.
        """
        try:
            clients = await self._get_clients()
        except Exception:
            logger.exception("watcher: failed to fetch client list")
            return 0

        dispatched = 0
        for client in clients:
            try:
                items = await client.list_managed_downloads()
            except Exception:
                logger.exception(
                    "watcher: client_id=%s list_managed_downloads failed — "
                    "isolating and continuing",
                    getattr(client, "client_id", "<unknown>"),
                )
                continue

            for item in items:
                if item.imported:
                    continue
                key = (item.client_id, item.client_native_id)
                if key in self._seen:
                    continue
                self._record_seen(key)
                try:
                    await self._dispatcher(item)
                    dispatched += 1
                except Exception:
                    logger.exception(
                        "watcher: dispatcher raised on (%s, %s)",
                        item.client_id,
                        item.client_native_id,
                    )
        return dispatched

    async def _run(self) -> None:
        """Internal loop body — tick → wait → repeat until stopped."""
        while not self._stop_event.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                continue

    def _record_seen(self, key: tuple[int, str]) -> None:
        """Add to the dedup set with FIFO eviction at the cap."""
        self._seen.add(key)
        self._seen_order.append(key)
        if len(self._seen_order) > _DEDUP_CAP:
            evicted = self._seen_order.pop(0)
            self._seen.discard(evicted)


__all__ = ["DEFAULT_INTERVAL_SECONDS", "WatcherLoop"]
