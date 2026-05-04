"""Lifespan-integrated heartbeat loop (spec 009 T030).

The pure primitives (`HeartbeatProbe`, `run_heartbeat_pass`) live in
``heartbeat.py``; this module adds the I/O bookkeeping that turns
them into a long-running background task:

* loads :class:`LibrarySnapshot` rows from the DB once per tick,
* persists the new ``library.status`` whenever the probe sees a
  transition,
* publishes :class:`HeartbeatEvent` instances on the spec 011
  :class:`EventChannel` so operator-configured notification
  targets (Apprise URLs, webhooks) see ``OnHealthIssue`` events
  the moment a library mountpoint flaps down or recovers.

Loop cadence is fixed to 5 s — `run_heartbeat_pass` itself
respects each library's ``heartbeat_seconds`` so a 30-second-
configured library still only fires every 30 s. The 5 s tick is
the floor: it prevents a 5-second-cadence library from being
starved by a slower-cadence sibling, and keeps shutdown latency
bounded.

Failures inside one library's probe never interrupt the loop —
the per-library probe already swallows ``OSError`` into the
``UNAVAILABLE`` status; everything else is wrapped in a
try/except so a malformed row can't take down the whole loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from romarr.libraries._debounce import WindowedDebouncer
from romarr.libraries.heartbeat import (
    HeartbeatProbe,
    run_heartbeat_pass,
)
from romarr.libraries.models import Library
from romarr.libraries.types import LibrarySnapshot, LibraryStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from romarr.libraries.heartbeat import HeartbeatEvent
    from romarr.notifications.channel import EventChannel


_logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 5.0
"""Floor cadence for the loop driver. Per-library cadence
(``library.heartbeat_seconds``, default 30 s) is still enforced
inside ``run_heartbeat_pass``; this floor just bounds shutdown
latency + caps starvation when one library has a 5-second
cadence."""

_DEFAULT_DEBOUNCE_WINDOW = timedelta(minutes=5)
"""Mirror of FR-029 — same window the pure primitive uses."""


def _snapshot_from_row(row: Library) -> LibrarySnapshot:
    """Project a :class:`Library` ORM row to the frozen snapshot
    shape the heartbeat primitives consume.

    Status is read off the row so the first observation only
    fires when the persisted state disagrees with what's on
    disk; subsequent observations refresh in-place via the
    probe's ``_last_status``."""
    accepted_ids: frozenset[int] = frozenset()
    if row.platforms_restricted:
        # The m2m is loaded lazily; the heartbeat doesn't need
        # the platform list (the probe only looks at the path),
        # so we pass an empty allowlist when restriction is on.
        # The routing engine reads this for real via its own
        # query — heartbeat just stat()s the path.
        accepted_ids = frozenset()
    return LibrarySnapshot(
        id=row.id,
        name=row.name,
        path=row.path,
        status=LibraryStatus(row.status),
        platforms_restricted=row.platforms_restricted,
        accepted_platform_ids=accepted_ids,
        quality_profile_id=row.quality_profile_id,
        region_profile_id=row.region_profile_id,
        dump_profile_id=row.dump_profile_id,
        language_profile_id=row.language_profile_id,
        naming_profile_id=row.naming_profile_id,
        use_hardlinks=row.use_hardlinks,
        lifecycle_policy=row.lifecycle_policy,
        keep_dump_history=row.keep_dump_history,
        min_disk_free_gb=row.min_disk_free_gb,
        preserve_archive=row.preserve_archive,
    )


async def _load_library_snapshots(
    session: AsyncSession,
) -> tuple[list[LibrarySnapshot], dict[int, int]]:
    """Read every Library row + its per-row heartbeat cadence.

    Returns ``(snapshots, cadence_map)`` so the caller doesn't
    need to re-query for the cadence dict ``run_heartbeat_pass``
    expects."""
    rows = (
        (await session.execute(select(Library)))
        .scalars()
        .all()
    )
    snapshots = [_snapshot_from_row(r) for r in rows]
    cadence = {r.id: r.heartbeat_seconds for r in rows}
    return snapshots, cadence


async def _persist_transitions(
    *,
    session: AsyncSession,
    events: list[HeartbeatEvent],
) -> None:
    """Write the new status for each library that transitioned.

    Skips rows that have already been deleted (rare race when an
    operator removes a library mid-tick) by the simple expedient
    of letting the UPDATE affect zero rows."""
    if not events:
        return
    for event in events:
        await session.execute(
            update(Library)
            .where(Library.id == event.library_id)
            .values(status=event.status.value)
        )
    await session.commit()


class HeartbeatLoop:
    """Background heartbeat driver.

    Lifecycle:

    * :meth:`start` — spawn the background task. Idempotent: a
      second call while the loop is running raises a guard
      (catches the obvious "called twice" misuse).
    * :meth:`stop` — cancel the task and await its exit. Safe to
      call multiple times; subsequent calls are no-ops.

    The loop is intentionally simple — one tick every 5 s, run
    the pure primitive, persist the events. The scheduler
    (spec 012) is not used here because the heartbeat is
    operationally a long-running background task, not a cron
    job: it has its own cadence model (per-library
    ``heartbeat_seconds``) and its own notification path
    (``EventChannel`` directly, not via the audit ledger).
    """

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        event_channel: EventChannel | None = None,
        tick_seconds: float = _DEFAULT_TICK_SECONDS,
        debounce_window: timedelta = _DEFAULT_DEBOUNCE_WINDOW,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._event_channel = event_channel
        self._tick_seconds = tick_seconds
        self._debouncer: WindowedDebouncer[tuple[int, LibraryStatus]] = (
            WindowedDebouncer(window=debounce_window)
        )
        self._probes: dict[int, HeartbeatProbe] = {}
        self._last_run: dict[int, datetime] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Spawn the background tick task."""
        if self._task is not None and not self._task.done():
            raise RuntimeError("HeartbeatLoop already started")
        self._task = asyncio.create_task(self._run(), name="heartbeat-loop")

    async def stop(self) -> None:
        """Cancel the background task and await its exit."""
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None

    async def tick_once(self) -> list[HeartbeatEvent]:
        """Run one heartbeat pass synchronously.

        Exposed so tests + the manual ``romarr heartbeat`` CLI
        (when it lands) can drive the loop deterministically.
        Returns the events emitted on this pass — the loop
        ignores the return value, but callers may want to
        inspect it."""
        async with self._sessionmaker() as session:
            snapshots, cadence = await _load_library_snapshots(session)

        events = run_heartbeat_pass(
            snapshots=snapshots,
            probes=self._probes,
            last_run=self._last_run,
            cadence=cadence,
            now=datetime.now(UTC),
            debouncer=self._debouncer,
        )

        if events:
            async with self._sessionmaker() as session:
                await _persist_transitions(session=session, events=events)

            if self._event_channel is not None:
                for event in events:
                    try:
                        await self._event_channel.publish(event)
                    except Exception:
                        # A bad subscriber must not poison the
                        # loop; the channel itself logs the
                        # underlying error.
                        _logger.exception(
                            "heartbeat_loop.publish_failed",
                            extra={"library_id": event.library_id},
                        )

        return events

    async def _run(self) -> None:
        """Inner loop driver. Cancellation-aware: a single
        :class:`asyncio.CancelledError` exits cleanly."""
        try:
            while True:
                try:
                    await self.tick_once()
                except Exception:
                    # Any error short of CancelledError shouldn't
                    # kill the loop — log + retry next tick.
                    _logger.exception("heartbeat_loop.tick_failed")
                await asyncio.sleep(self._tick_seconds)
        except asyncio.CancelledError:
            raise


__all__ = ["HeartbeatLoop"]
