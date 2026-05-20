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
from romarr.importer.models import ImportHistory

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


# Canonical ``DownloadState`` (the implementation's normalised
# enum from ``romarr.downloaders.types``) → ``queue_entry.state``
# vocabulary. ``seeding`` collapses to ``completed`` because as
# far as the operator's queue UI is concerned the file is on
# disk; the torrent client may keep seeding but the next stage
# (import) only cares about the on-disk state. ``stalled`` maps
# to ``stuck`` since that's the operator-facing label the API
# router whitelists.
_STATE_MAP: dict[str, str] = {
    "queued": "queued",
    "downloading": "downloading",
    "paused": "paused",
    "completed": "completed",
    "seeding": "completed",
    "stalled": "stuck",
    "failed": "failed",
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
    updated = 0
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(QueueEntry).where(QueueEntry.state.in_(_ACTIVE_STATES))
            )
        ).scalars().all()

        # No active downloads is the common case right after a
        # restart — but completed-but-unimported orphans may
        # still need the recovery pass below, so we fall through
        # instead of returning early.
        # Group rows by client so we instantiate each client once
        # per tick instead of one per row. Rows with a NULL client
        # id are Romarr-internal downloads (URL-sourced ROM packs
        # streamed by the ingest pipeline — slice 465); they have
        # no client to poll, so the reconciler leaves them alone.
        by_client: dict[int, list[QueueEntry]] = {}
        for row in rows:
            if row.download_client_id is None:
                continue
            by_client.setdefault(row.download_client_id, []).append(row)

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
                    # Slice 438 — pull the typed error from
                    # ``DownloadStatus.error`` (populated by the
                    # streamer / qBit / SAB when they have a
                    # specific failure to surface) instead of
                    # always blanking ``error_msg``. Lets the
                    # queue page + History tab show
                    # "checksum_mismatch", "upstream 404", "CF
                    # challenge" inline instead of operators
                    # having to grep the container logs.
                    new_error: str | None = None
                    if new_state == "failed":
                        new_error = status.error
                    if (
                        row.progress == new_progress
                        and row.state == new_state
                        and row.eta_seconds == status.eta_seconds
                        and (new_size is None or row.size_bytes == new_size)
                        and row.error_msg == new_error
                    ):
                        # Nothing moved — skip the write so we
                        # don't bump ``last_updated_at`` and
                        # cause a no-op websocket fan-out.
                        continue
                    previous_state = row.state
                    row.state = new_state
                    row.progress = new_progress
                    row.eta_seconds = status.eta_seconds
                    if new_size is not None:
                        row.size_bytes = new_size
                    row.error_msg = new_error
                    row.last_updated_at = now
                    # Slice 454 — durably capture where the file
                    # landed. The grabarr-direct client only keeps
                    # this in its in-memory ``_pending`` dict; by
                    # mirroring it onto the row here (every tick
                    # while the download is still ``active``) the
                    # completed file survives a container restart
                    # and the recovery pass below can still find
                    # it.
                    if status.save_path:
                        row.content_path = status.save_path
                    updated += 1

                    # Slice 438 — emit a synthetic ImportHistory row
                    # the moment a queue entry transitions to FAILED
                    # so the Activity → History tab shows the
                    # operator-facing failure ("CF challenge",
                    # "checksum_mismatch", "upstream 404", etc.)
                    # without them having to read container logs.
                    # ``imported_via='download_failed'`` is a
                    # distinct value (CHECK widened by migration
                    # 0025) so the UI / queries can filter these
                    # apart from actual import-pipeline failures.
                    if (
                        previous_state != "failed"
                        and new_state == "failed"
                    ):
                        import uuid as _uuid
                        session.add(
                            ImportHistory(
                                source_path=row.title or row.download_client_native_id,
                                dest_path=status.save_path,
                                download_client_id=row.download_client_id,
                                download_client_native_id=row.download_client_native_id,
                                game_id=row.game_id,
                                release_id=row.release_id,
                                dump_id=None,
                                source_hash_sha1=None,
                                confidence=None,
                                imported_via="download_failed",
                                success=False,
                                coalesced=False,
                                warning=None,
                                error_msg=new_error or "download failed",
                                imported_by="reconciler",
                                correlation_id=str(_uuid.uuid4()),
                                started_at=now,
                                finished_at=now,
                                duration_ms=0,
                            )
                        )
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

    # Slice 454 — recovery pass for completed-but-never-imported
    # rows. The watcher drives imports off the download client's
    # ``list_managed_downloads()``, which for grabarr-direct is
    # backed by an in-memory dict — a container restart between
    # "download completed" and "watcher dispatched" loses the
    # trigger and the file sits orphaned. We persisted
    # ``content_path`` above while the download was active, so
    # here we can find any ``completed`` row whose import never
    # ran and dispatch it directly. ``import_attempted_at`` is
    # stamped first (and committed) so a slow ``run_import``
    # can't be double-dispatched on the next tick.
    recovered = await _recover_orphaned_completions(session_factory)
    return updated + recovered


async def _recover_orphaned_completions(
    session_factory: SessionFactory,
) -> int:
    """Dispatch imports for completed downloads the watcher missed.

    Returns the number of rows handed to ``run_import``.
    """
    import os
    from datetime import UTC, datetime as _dt

    from romarr.importer._dispatch import build_managed_download_dispatcher
    from romarr.downloaders.types import ManagedDownload

    async with session_factory() as session:
        orphans = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.state == "completed",
                    QueueEntry.content_path.is_not(None),
                    QueueEntry.import_attempted_at.is_(None),
                )
            )
        ).scalars().all()
        if not orphans:
            return 0
        now = _dt.now(UTC)
        dispatchable: list[QueueEntry] = []
        for row in orphans:
            # Romarr-internal downloads (NULL client — slice 465)
            # never go through the watcher dispatcher; their
            # ingest pipeline owns the post-download steps.
            if row.download_client_id is None:
                continue
            path = row.content_path or ""
            if not path or not os.path.exists(path):
                # File genuinely gone (disk-full cleanup, manual
                # delete, …) — stamp it so we stop re-checking and
                # surface it as failed for the operator.
                row.import_attempted_at = now
                row.state = "failed"
                row.error_msg = (
                    row.error_msg or "completed file missing on disk"
                )
                continue
            row.import_attempted_at = now
            dispatchable.append(row)
        # Commit the stamps BEFORE running any import so a crash
        # mid-dispatch can't replay the same rows.
        await session.commit()

    if not dispatchable:
        return 0

    dispatcher = build_managed_download_dispatcher(session_factory)
    recovered = 0
    for row in dispatchable:
        try:
            await dispatcher(
                ManagedDownload(
                    client_id=row.download_client_id,
                    client_native_id=row.download_client_native_id,
                    name=row.title or row.download_client_native_id,
                    save_path=row.content_path or "",
                    imported=False,
                )
            )
            recovered += 1
        except Exception:
            logger.exception(
                "queue_reconciler: recovery dispatch failed for "
                "queue_entry native_id=%s",
                row.download_client_native_id,
            )
    if recovered:
        logger.info(
            "queue_reconciler: recovered %d orphaned completed "
            "download(s) the watcher missed",
            recovered,
        )
    return recovered


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
