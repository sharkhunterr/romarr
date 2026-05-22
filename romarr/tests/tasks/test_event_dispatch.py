"""Spec 011 → scheduler dispatch glue tests (slice 278 / T048).

Verifies that the event dispatcher subscribes globally on the
``EventChannel`` and fires the right ``SchedulerService.trigger``
call when an ``OnGameAdded`` payload lands.

The scheduler is replaced with a stand-in that records every
``trigger`` call so the test doesn't need a real APScheduler.
"""

from __future__ import annotations

import logging

import pytest

from romarr.notifications.channel import EventChannel
from romarr.notifications.types import (
    GameRef,
    OnGameAddedPayload,
    OnHealthIssuePayload,
    HealthStatus,
)
from romarr.tasks.errors import JobAlreadyRunning
from romarr.tasks.event_dispatch import attach_event_dispatch


class _SchedulerStub:
    """Records every ``trigger`` call so the test can assert
    the dispatcher fired with the right parameters."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def trigger(
        self,
        job_id: str,
        *,
        parameters: dict | None = None,
        force: bool = False,
    ) -> int:
        self.calls.append((job_id, dict(parameters or {})))
        return 1


def _game_ref(game_id: int = 42) -> GameRef:
    return GameRef(
        id=game_id,
        title="Sonic the Hedgehog",
        platform_slug="megadrive",
        platform_name="Mega Drive",
    )


@pytest.mark.asyncio
async def test_on_game_added_fires_auto_check_added() -> None:
    scheduler = _SchedulerStub()
    channel = EventChannel()
    attach_event_dispatch(channel, scheduler)  # type: ignore[arg-type]

    await channel.publish(OnGameAddedPayload(game=_game_ref(42)))

    assert len(scheduler.calls) == 1
    job_id, params = scheduler.calls[0]
    assert job_id == "AutoCheckAdded"
    assert params == {"gameId": 42}


@pytest.mark.asyncio
async def test_unrelated_event_does_not_fire_trigger() -> None:
    """Only events in the dispatch table fire — an OnHealthIssue
    payload arriving on the channel must NOT trigger AutoCheckAdded.
    """
    scheduler = _SchedulerStub()
    channel = EventChannel()
    attach_event_dispatch(channel, scheduler)  # type: ignore[arg-type]

    await channel.publish(
        OnHealthIssuePayload(
            component="indexer-1",
            category="indexer",
            severity="warning",
            previous_status=HealthStatus.OK,
            current_status=HealthStatus.WARNING,
            message="rate-limit exceeded",
        )
    )
    assert scheduler.calls == []


@pytest.mark.asyncio
async def test_unsubscribe_stops_dispatch() -> None:
    """``unsubscribe_global`` removes the handler so future
    publishes don't fire triggers (used during shutdown)."""
    scheduler = _SchedulerStub()
    channel = EventChannel()
    handler = attach_event_dispatch(channel, scheduler)  # type: ignore[arg-type]

    channel.unsubscribe_global(handler)
    await channel.publish(OnGameAddedPayload(game=_game_ref()))
    assert scheduler.calls == []


@pytest.mark.asyncio
async def test_trigger_failure_does_not_propagate() -> None:
    """Even if ``trigger`` raises, the channel publish loop
    must complete cleanly — best-effort delivery."""

    class _BoomScheduler:
        async def trigger(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("scheduler down")

    channel = EventChannel()
    attach_event_dispatch(channel, _BoomScheduler())  # type: ignore[arg-type]

    # Publishing must NOT raise even though trigger fails.
    await channel.publish(OnGameAddedPayload(game=_game_ref()))


@pytest.mark.asyncio
async def test_job_already_running_is_not_logged_as_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``AutoCheckAdded`` is single-instance: when games are added
    back-to-back (e.g. a request manager dispatching a batch of
    approvals) a later ``OnGameAdded`` trigger raises
    ``JobAlreadyRunning``. That is benign and must be swallowed as a
    debug note — never surfaced as an ERROR.
    """

    class _BusyScheduler:
        async def trigger(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise JobAlreadyRunning("AutoCheckAdded already at max")

    channel = EventChannel()
    attach_event_dispatch(channel, _BusyScheduler())  # type: ignore[arg-type]

    with caplog.at_level(logging.DEBUG, logger="romarr.tasks.event_dispatch"):
        await channel.publish(OnGameAddedPayload(game=_game_ref()))

    # Only inspect the dispatcher's own records — a full-suite run
    # can leak unrelated ERROR logs from other components into
    # caplog, which has nothing to do with this behaviour.
    dispatch_records = [
        r for r in caplog.records if r.name == "romarr.tasks.event_dispatch"
    ]
    # No ERROR-level record from the dispatcher …
    assert not [r for r in dispatch_records if r.levelno >= logging.ERROR]
    # … and the skip is recorded at debug.
    assert any(
        "already running" in r.getMessage() for r in dispatch_records
    )
