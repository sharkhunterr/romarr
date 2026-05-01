"""EventChannel tests (T015, T016, FR-026, FR-027)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from romarr.notifications.channel import EventChannel


@pytest.fixture
def small_channel() -> EventChannel:
    """A 5-event-cap channel makes back-pressure tests fast."""
    return EventChannel(max_buffer=5)


# ---------------------------------------------------------------------------
# T015 — back-pressure caps and drops oldest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_back_pressure_drops_oldest_when_full(
    small_channel: EventChannel,
) -> None:
    """Subscribers register but never start their dispatcher loop,
    so the queue fills up. The 6th publish drops the oldest entry
    in that notification's queue and increments dropped_count
    (FR-026, SC-008)."""
    received: list[Any] = []

    async def slow(_event: Any) -> None:
        await asyncio.sleep(60)  # never returns during the test
        received.append(_event)

    small_channel.subscribe(notification_id=1, callback=slow)

    for i in range(6):
        await small_channel.publish({"event_type": "OnImport", "i": i})

    # Five events sit in the queue; one was dropped.
    assert small_channel.dropped_count(1) == 1
    queue = small_channel._queues[1]
    drained: list[dict[str, Any]] = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    # Oldest (i=0) was dropped; remaining are i=1..5.
    assert [e["i"] for e in drained] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_dropped_count_per_notification() -> None:
    """The drop counter is per-notification — a slow consumer
    doesn't lose events for a fast one. We can't ``drain()`` the
    slow consumer's queue (its callback never returns), so we
    publish with explicit yields between events to let the fast
    dispatcher drain between publishes."""
    channel = EventChannel(max_buffer=2)
    blocked = asyncio.Event()

    async def never(_event: Any) -> None:
        blocked.set()
        await asyncio.sleep(60)

    received_b: list[Any] = []

    async def fast_b(event: Any) -> None:
        received_b.append(event)

    channel.subscribe(notification_id=1, callback=never)  # slow
    channel.subscribe(notification_id=2, callback=fast_b)  # fast

    await channel.start()
    try:
        for i in range(5):
            await channel.publish({"i": i})
            await asyncio.sleep(0.01)  # let fast dispatcher drain
    finally:
        await channel.stop()

    # 5 publishes; the slow dispatcher pulled the first event
    # (and is still blocked inside the callback) so the queue's
    # 2-slot cap fills with events 1+2; events 3 and 4 each push
    # a drop. Result: 2 drops, not 3.
    assert channel.dropped_count(1) == 2
    assert channel.dropped_count(2) == 0  # fast consumer kept up
    assert len(received_b) == 5
    assert blocked.is_set()


# ---------------------------------------------------------------------------
# T016 — serial per-notification, parallel across notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serial_per_notification() -> None:
    """Within one notification, callbacks run one at a time. The
    test publishes A then B then C; the callback records (notif_id,
    event) when it ENTERS, sleeps briefly, records when it EXITS.
    The result must be A-enter / A-exit / B-enter / B-exit / etc.
    for each notification's stream."""
    channel = EventChannel(max_buffer=10)
    timeline_a: list[str] = []
    timeline_b: list[str] = []

    async def callback_a(event: Any) -> None:
        timeline_a.append(f"enter-{event['i']}")
        await asyncio.sleep(0.01)
        timeline_a.append(f"exit-{event['i']}")

    async def callback_b(event: Any) -> None:
        timeline_b.append(f"enter-{event['i']}")
        await asyncio.sleep(0.01)
        timeline_b.append(f"exit-{event['i']}")

    channel.subscribe(notification_id=1, callback=callback_a)
    channel.subscribe(notification_id=2, callback=callback_b)
    await channel.start()
    try:
        for i in range(3):
            await channel.publish({"i": i})
        await channel.drain(timeout=1.0)
    finally:
        await channel.stop()

    assert timeline_a == [
        "enter-0",
        "exit-0",
        "enter-1",
        "exit-1",
        "enter-2",
        "exit-2",
    ]
    assert timeline_b == [
        "enter-0",
        "exit-0",
        "enter-1",
        "exit-1",
        "enter-2",
        "exit-2",
    ]


@pytest.mark.asyncio
async def test_parallel_across_notifications() -> None:
    """Two notifications run their callbacks **concurrently** —
    a 100ms sleep on subscriber A doesn't block subscriber B."""
    channel = EventChannel(max_buffer=10)
    a_started = asyncio.Event()
    b_started = asyncio.Event()

    async def callback_a(_event: Any) -> None:
        a_started.set()
        # Wait for B to also start before returning so the test
        # can verify both ran in parallel.
        await asyncio.wait_for(b_started.wait(), timeout=1.0)

    async def callback_b(_event: Any) -> None:
        b_started.set()
        await asyncio.wait_for(a_started.wait(), timeout=1.0)

    channel.subscribe(notification_id=1, callback=callback_a)
    channel.subscribe(notification_id=2, callback=callback_b)

    await channel.start()
    try:
        await channel.publish({"i": 0})
        # If callbacks ran serially globally, this would deadlock
        # (A waits for B, B waits for A) and time out.
        await asyncio.wait_for(
            asyncio.gather(a_started.wait(), b_started.wait()),
            timeout=1.0,
        )
    finally:
        await channel.stop()


# ---------------------------------------------------------------------------
# Subscriber failures don't poison the channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscriber_failure_recorded_and_dispatch_continues() -> None:
    channel = EventChannel(max_buffer=10)
    received: list[Any] = []
    fail_first = True

    async def flaky(event: Any) -> None:
        nonlocal fail_first
        if fail_first:
            fail_first = False
            raise RuntimeError("kaboom")
        received.append(event)

    channel.subscribe(notification_id=1, callback=flaky)
    await channel.start()
    try:
        await channel.publish({"i": 0})
        await channel.publish({"i": 1})
        await channel.drain(timeout=1.0)
    finally:
        await channel.stop()

    # First call failed; the second succeeded. last_error is None
    # because the most recent call was the success.
    assert received == [{"i": 1}]
    assert channel.last_error(1) is None


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsubscribe_cancels_task_and_drops_queue() -> None:
    channel = EventChannel(max_buffer=5)

    async def callback(_event: Any) -> None:
        pass

    channel.subscribe(notification_id=1, callback=callback)
    await channel.start()
    assert 1 in channel._tasks

    channel.unsubscribe(1)
    # Give the cancellation a moment to propagate.
    await asyncio.sleep(0.01)
    assert 1 not in channel._tasks
    assert 1 not in channel._queues
    await channel.stop()


def test_max_buffer_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        EventChannel(max_buffer=0)
