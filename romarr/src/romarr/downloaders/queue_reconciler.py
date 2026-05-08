"""Queue progress poller (slice 367).

The importer's ``WatcherLoop`` only fires on *completed*
downloads — it ignores anything still in flight. So a queue_entry
inserted by ``manual_grab`` at ``state='downloading'`` /
``progress=0.0`` was correct at insertion time but never moved
forward, even when qBit / SAB had finished the transfer. The
operator saw the row stuck at 0% in Activity → Queue.

This module owns the live-progress story: every
``DEFAULT_INTERVAL_SECONDS`` it pulls every active ``queue_entry``
row, calls ``client.get_status(native_id)`` per client, and
writes ``progress`` / ``state`` / ``eta_seconds`` /
``size_bytes`` / ``error_msg`` back. The watcher remains in
charge of the "imported once, never again" gate; this loop
strictly mirrors the in-flight queue.

The reconciler is bounded:

  * inactive states (``completed`` / ``failed``) are skipped — no
    point asking qBit about a torrent we already imported;
  * a client raising on ``get_status`` is logged and isolated:
    its rows stay where they were, the rest of the rows for
    other clients still get updated.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.api.models import QueueEntry
from romarr.downloaders.errors import (
    AuthError,
    ConnectionError as DownloaderConnError,
    VersionError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.downloaders.base import DownloadClient


logger = logging.getLogger(__name__)


DEFAULT_INTERVAL_SECONDS = 30.0
"""Match the importer watcher cadence — same trade-off."""


_ACTIVE_STATES = ("queued", "downloading", "paused", "stuck", "pending_retry")
"""Rows we still query the client about. ``completed`` /
``failed`` rows are terminal — the watcher's import path owns
them now, polling them again would just churn write traffic."""


# qBit / SAB free-form state strings → the canonical
# ``queue_entry.state`` enum the API + UI render. Anything we
# can't map keeps the existing row state to avoid lying to the
# operator.
_STATE_MAP: dict[str, str] = {
    "queued": "queued",
    "downloading": "downloading",
    "paused": "paused",
    "completed": "completed",
    "failed": "failed",
    "stuck": "stuck",
    "pending_retry": "pending_retry",
}


SessionFactory = Callable[[], "AsyncSession"]
"""``async def factory()`` returning a session — the lifespan
provides this so the loop can open a fresh session per tick
without coupling to a global engine here."""


ClientFactory = Callable[[int], Awaitable["DownloadClient"]]
"""Same shape as ``make_download_client_factory`` returns."""


async def reconcile_once(
    *,
    session_factory: SessionFactory,
    client_factory: ClientFactory,
) -> int:
    """Run one poll cycle. Returns the number of rows updated.

    Public so tests + a manual "refresh queue" endpoint can
    trigger a single tick without spinning up the loop.
    """
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(QueueEntry).where(QueueEntry.state.in_(_ACTIVE_STATES))
            )
        ).scalars().all()

        if not rows:
            return 0

        # Group rows by client so we instantiate each client once
        # per tick instead of one per row.
        by_client: dict[int, list[QueueEntry]] = {}
        for row in rows:
            by_client.setdefault(row.download_client_id, []).append(row)

        updated = 0
        now = datetime.now(UTC)
        for client_id, client_rows in by_client.items():
            try:
                client = await client_factory(client_id)
            except Exception:
                logger.exception(
                    "queue_reconciler: build client_id=%s failed — skipping its %d rows",
                    client_id,
                    len(client_rows),
                )
                continue
            try:
                for row in client_rows:
                    try:
                        status = await client.get_status(
                            row.download_client_native_id
                        )
                    except (
                        AuthError,
                        DownloaderConnError,
                        VersionError,
                    ) as exc:
                        # Surface the failure on the row but keep
                        # the loop going.
                        row.error_msg = f"{type(exc).__name__}: {exc}"
                        row.last_updated_at = now
                        updated += 1
                        continue
                    except Exception:
                        logger.exception(
                            "queue_reconciler: get_status client_id=%s native=%s failed",
                            client_id,
                            row.download_client_native_id,
                        )
                        continue

                    new_state = _STATE_MAP.get(
                        status.state, row.state
                    )
                    new_progress = float(status.progress)
                    new_size = status.total_bytes
                    if (
                        row.progress == new_progress
                        and row.state == new_state
                        and row.eta_seconds == status.eta_seconds
                        and (new_size is None or row.size_bytes == new_size)
                        and row.error_msg is None
                    ):
                        # Nothing moved — skip the write so we
                        # don't bump ``last_updated_at`` and
                        # cause a no-op websocket fan-out.
                        continue
                    row.state = new_state
                    row.progress = new_progress
                    row.eta_seconds = status.eta_seconds
                    if new_size is not None:
                        row.size_bytes = new_size
                    row.error_msg = None
                    row.last_updated_at = now
                    updated += 1
            finally:
                close = getattr(client, "aclose", None)
                if close is not None:
                    try:
                        await close()
                    except Exception:
                        logger.exception(
                            "queue_reconciler: aclose client_id=%s failed",
                            client_id,
                        )

        if updated:
            await session.commit()
        return updated


class QueueReconcilerLoop:
    """Background polling task — one tick every
    ``interval_seconds``. Public ``start`` / ``stop`` mirror the
    importer's ``WatcherLoop`` shape so the lifespan can manage
    them with the same idiom."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        client_factory: ClientFactory,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name="queue_reconciler_loop"
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await reconcile_once(
                    session_factory=self._session_factory,
                    client_factory=self._client_factory,
                )
            except Exception:
                logger.exception("queue_reconciler: tick raised; continuing")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                continue


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "QueueReconcilerLoop",
    "reconcile_once",
]
