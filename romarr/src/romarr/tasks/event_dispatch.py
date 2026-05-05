"""Spec 011 event → scheduler dispatch glue (slice 278 / T048).

Some scheduler jobs are *event-driven* — they don't run on a cron
or interval, they fire when a specific spec 011 event is published
on the in-process :class:`EventChannel`. The canonical one today is
``AutoCheckAdded``: when an ``OnGameAdded`` payload lands, the
``AutoCheckAddedAdapter`` runs one manual search round for the new
Game so the operator doesn't have to flip to Wanted manually.

The dispatcher is a thin global subscriber:

  * registered on app startup via ``attach_event_dispatch``
  * filters the channel's stream by ``event_type``
  * when a known event arrives, calls
    :meth:`SchedulerService.trigger` with the appropriate job
    + parameters
  * trigger failures are logged but never propagate back into the
    channel's publish loop (best-effort delivery, matches the WS
    bridge's contract)

The mapping is intentionally small + table-driven so adding a new
event-driven job is a one-line change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from romarr.notifications.types import EventType

if TYPE_CHECKING:
    from romarr.notifications.channel import EventChannel
    from romarr.tasks.scheduler import SchedulerService

_logger = logging.getLogger(__name__)


def _params_for_game_added(event: Any) -> dict[str, Any]:
    """Build the ``AutoCheckAdded`` parameters from an
    ``OnGameAddedPayload`` instance."""
    game = getattr(event, "game", None)
    if game is None:
        return {}
    game_id = getattr(game, "id", None)
    if game_id is None:
        return {}
    return {"gameId": int(game_id)}


# (event_type, job_id, params_builder). Adding a new entry below
# is the only change needed to wire a new event-driven job.
_DISPATCH_TABLE: list[
    tuple[EventType, str, "Any"],
] = [
    (EventType.ON_GAME_ADDED, "AutoCheckAdded", _params_for_game_added),
]


class _EventDispatcher:
    """Holds a reference to the scheduler so the global
    subscriber can call ``trigger`` without re-importing the
    service every time."""

    def __init__(self, scheduler: "SchedulerService") -> None:
        self._scheduler = scheduler

    async def __call__(self, event: Any) -> None:
        et = getattr(event, "event_type", None)
        if et is None:
            return
        try:
            event_type = EventType(et) if isinstance(et, str) else et
        except ValueError:
            return

        for trigger_type, job_id, builder in _DISPATCH_TABLE:
            if trigger_type != event_type:
                continue
            params = builder(event)
            if not params:
                # The builder rejected this payload (missing fields,
                # etc.); log so the operator can see the silent
                # drop without it crashing the channel.
                _logger.warning(
                    "event-dispatch %s → %s skipped (no params)",
                    event_type,
                    job_id,
                )
                return
            try:
                await self._scheduler.trigger(job_id, parameters=params)
            except Exception:
                _logger.exception(
                    "event-dispatch %s → %s trigger failed",
                    event_type,
                    job_id,
                )
            return


def attach_event_dispatch(
    channel: "EventChannel",
    scheduler: "SchedulerService",
) -> _EventDispatcher:
    """Subscribe the dispatcher globally to ``channel``. Returns the
    handler so callers can ``unsubscribe_global`` on shutdown.
    """
    dispatcher = _EventDispatcher(scheduler)
    channel.subscribe_global(dispatcher)
    return dispatcher


__all__ = ["attach_event_dispatch"]
