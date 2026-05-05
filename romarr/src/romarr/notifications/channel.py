"""In-process notification event channel (FR-026, FR-027).

The producer side is the importer's :class:`ImporterEventBus`,
the library heartbeat / scanner / exporters, the search engine's
grab/fail emitters, the DAT auto-refresh, and the metadata
aggregator. The consumer side is each operator-configured
notification target.

The channel is intentionally simple:

  * One :class:`asyncio.Queue` **per notification**. Events
    fan-out to every subscriber whose subscription matches the
    event's type (the dispatcher decides match by reading the
    notification row's ``on_*`` flags).
  * Each per-notification queue caps at 10 000 events
    (FR-026 / SC-008). On overflow the **oldest** event is
    dropped and ``dropped_count`` increments — a structured
    warning the operator can monitor without needing a
    notification of its own.
  * Each notification has its **own dispatcher task** so
    delivery is serial per-notification (FR-027 — operator's
    Discord channel sees events in order) and parallel across
    notifications (the slow Slack target doesn't backpressure
    the fast Discord target).

Failures inside a subscriber's callback are caught and recorded
as ``last_error_per_notification[notification_id]``; the
dispatcher keeps draining so one bad target doesn't poison the
whole channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)

_MAX_BUFFER_DEFAULT = 10_000


type _Subscriber = Callable[[Any], Awaitable[None]]


class EventChannel:
    """Per-notification fan-out queue with bounded buffers."""

    def __init__(self, *, max_buffer: int = _MAX_BUFFER_DEFAULT) -> None:
        if max_buffer <= 0:
            raise ValueError("max_buffer must be positive")
        self._max_buffer = max_buffer
        self._queues: dict[int, asyncio.Queue[Any]] = {}
        self._callbacks: dict[int, _Subscriber] = {}
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._dropped: dict[int, int] = {}
        self._last_errors: dict[int, str | None] = {}
        # Global subscribers receive every published event without
        # the operator-configured Notification.on_* gating. Used by
        # the WS bridge (spec 013 T068 / T072) to fan out
        # ``MessageType`` envelopes to live operator sessions.
        self._global_subscribers: list[_Subscriber] = []

    # ------------------------------------------------------------------
    # Subscription

    def subscribe(
        self, notification_id: int, callback: _Subscriber
    ) -> None:
        """Register ``callback`` for ``notification_id``.

        The dispatcher task is spawned the first time ``start()``
        is called (or immediately if ``start()`` already ran).
        """
        self._queues.setdefault(
            notification_id, asyncio.Queue(maxsize=self._max_buffer)
        )
        self._callbacks[notification_id] = callback
        self._dropped.setdefault(notification_id, 0)
        self._last_errors.setdefault(notification_id, None)

    def subscribe_global(self, callback: _Subscriber) -> None:
        """Register a global subscriber — called for every event
        regardless of any per-notification filter. The WS bridge
        uses this to fan-out events to live operator sessions
        (spec 013 T068 / T072). Idempotent on the same callback.
        """
        if callback not in self._global_subscribers:
            self._global_subscribers.append(callback)

    def unsubscribe_global(self, callback: _Subscriber) -> None:
        """Remove a previously-registered global subscriber."""
        with contextlib.suppress(ValueError):
            self._global_subscribers.remove(callback)

    def unsubscribe(self, notification_id: int) -> None:
        """Remove a subscriber (and cancel its dispatcher task)."""
        self._callbacks.pop(notification_id, None)
        task = self._tasks.pop(notification_id, None)
        if task is not None and not task.done():
            task.cancel()
        self._queues.pop(notification_id, None)
        self._dropped.pop(notification_id, None)
        self._last_errors.pop(notification_id, None)

    def dropped_count(self, notification_id: int) -> int:
        """Return how many events have been dropped from this
        notification's queue since :meth:`subscribe` (back-pressure
        signal — the operator can monitor this in the UI)."""
        return self._dropped.get(notification_id, 0)

    def last_error(self, notification_id: int) -> str | None:
        """Return the last subscriber-callback error message for
        ``notification_id`` (None when the most recent call
        succeeded)."""
        return self._last_errors.get(notification_id)

    # ------------------------------------------------------------------
    # Publish

    async def publish(self, event: Any) -> None:
        """Fan out ``event`` to every subscribed notification.

        Per FR-026 / SC-008, when the per-notification queue is
        full we drop the **oldest** event in that queue, log a
        structured warning, and increment ``dropped_count``. The
        new event always lands.

        Yields control once at the end via ``asyncio.sleep(0)``
        so dispatcher tasks get a chance to run between
        publishes — without this, a tight publish loop would
        starve the dispatcher and every queue would fill
        artificially.
        """
        for notification_id, queue in self._queues.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, retry. The drop matters per-
                # notification — a slow consumer doesn't lose
                # events for a fast one.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self._dropped[notification_id] += 1
                _logger.warning(
                    "notification queue overflow for "
                    "notification_id=%s; dropped oldest "
                    "(total dropped=%s)",
                    notification_id,
                    self._dropped[notification_id],
                )
                queue.put_nowait(event)
        # Global subscribers (WS bridge etc.) — best-effort: a
        # failing global subscriber is logged but never blocks
        # the per-notification flow.
        for cb in list(self._global_subscribers):
            try:
                await cb(event)
            except Exception:
                _logger.exception(
                    "global subscriber failed; dropping event for it"
                )
        await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # Lifecycle

    async def start(self) -> None:
        """Spawn one dispatcher task per subscribed notification.

        Idempotent: re-running after a subscribe/unsubscribe
        churn just spawns the missing tasks.
        """
        for notification_id in list(self._callbacks):
            existing = self._tasks.get(notification_id)
            if existing is not None and not existing.done():
                continue
            self._tasks[notification_id] = asyncio.create_task(
                self._dispatch_loop(notification_id),
                name=f"notification-dispatcher-{notification_id}",
            )

    async def stop(self) -> None:
        """Cancel every dispatcher task and await their teardown."""
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError, BaseException):
                await task
        self._tasks.clear()

    async def drain(self, *, timeout: float | None = None) -> None:
        """Wait until every per-notification queue has been fully
        processed — every published event has its ``task_done()``
        recorded (so in-flight callbacks have completed too).

        Useful in tests. Production lifespan teardown calls
        :meth:`stop` instead.
        """

        async def _wait() -> None:
            for queue in list(self._queues.values()):
                await queue.join()

        if timeout is None:
            await _wait()
        else:
            await asyncio.wait_for(_wait(), timeout=timeout)

    # ------------------------------------------------------------------
    # Dispatch loop

    async def _dispatch_loop(self, notification_id: int) -> None:
        queue = self._queues[notification_id]
        while True:
            event = await queue.get()
            callback = self._callbacks.get(notification_id)
            if callback is None:
                # Unsubscribed mid-flight; drop the event silently.
                queue.task_done()
                continue
            try:
                await callback(event)
                self._last_errors[notification_id] = None
            except asyncio.CancelledError:
                queue.task_done()
                raise
            except Exception as exc:
                # One subscriber's bug must not poison the channel.
                # Record + log; the dispatcher keeps draining.
                _logger.exception(
                    "notification subscriber failed for "
                    "notification_id=%s",
                    notification_id,
                )
                self._last_errors[notification_id] = (
                    f"{exc.__class__.__name__}: {exc}"
                )
            finally:
                queue.task_done()


__all__ = ["EventChannel"]
