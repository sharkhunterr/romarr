"""Progress throttle tests (T033, T034, FR-023, SC-008)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from romarr.tasks.execution.progress import ProgressBroadcaster


@pytest.fixture
def captured() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def broadcaster(
    captured: list[dict[str, Any]],
) -> ProgressBroadcaster:
    async def emit(event: dict[str, Any]) -> None:
        captured.append(event)

    # Tighten the throttle window so tests don't sit on
    # wall-clock waits — semantics are identical.
    return ProgressBroadcaster(emit=emit, window_seconds=0.1)


# ---------------------------------------------------------------------------
# T033 — at most 10 events per second per runId
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttling_caps_event_rate(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """A burst of 50 calls in < 100 ms produces at most 2
    events: the leading one (immediate) and the trailing one
    (flushed at the end of the quiet window)."""
    for i in range(50):
        await broadcaster.progress(
            job_run_id=1,
            current=i,
            total=50,
            message=f"step {i}",
        )

    # Wait long enough for the trailing flush to land.
    await asyncio.sleep(0.2)
    await broadcaster.aclose()

    # 1 leading + at most 1 trailing = ≤ 2 events.
    assert 1 <= len(captured) <= 2

    # The first event is the leading one — current=0.
    assert captured[0]["current"] == 0
    # The last event captures the latest (49) thanks to the
    # trailing flush replacing earlier pending events.
    assert captured[-1]["current"] == 49


@pytest.mark.asyncio
async def test_throttle_per_run_id(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """Throttle scope is per-runId: two concurrent runs each
    emit independently."""
    await broadcaster.progress(
        job_run_id=1, current=1, total=10, message="run-1"
    )
    await broadcaster.progress(
        job_run_id=2, current=1, total=10, message="run-2"
    )
    await broadcaster.aclose()

    by_run = {e["jobRunId"]: e for e in captured}
    assert 1 in by_run
    assert 2 in by_run


@pytest.mark.asyncio
async def test_calls_separated_by_window_all_emit(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """Calls separated by ≥ window_seconds all emit immediately
    — the throttle only collapses bursts."""
    for i in range(3):
        await broadcaster.progress(
            job_run_id=1, current=i, total=3, message=""
        )
        await asyncio.sleep(0.12)
    await broadcaster.aclose()

    # 3 leading emissions (each spaced > 100 ms apart).
    assert len(captured) == 3
    assert [e["current"] for e in captured] == [0, 1, 2]


# ---------------------------------------------------------------------------
# T034 — final taskFinished event always fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finished_event_bypasses_throttle(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """Even when called inside the quiet window, the terminal
    ``taskFinished`` event fires immediately so the UI sees
    the final state."""
    await broadcaster.progress(
        job_run_id=1, current=1, total=10, message="working"
    )
    # Immediately emit terminal — within the quiet window.
    await broadcaster.finished(
        job_run_id=1,
        status="success",
        items_processed=10,
        message="all done",
    )
    await broadcaster.aclose()

    finished_events = [
        e for e in captured if e.get("eventType") == "taskFinished"
    ]
    assert len(finished_events) == 1
    assert finished_events[0]["status"] == "success"
    assert finished_events[0]["itemsProcessed"] == 10


@pytest.mark.asyncio
async def test_finished_clears_pending_trailing_event(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """After ``finished``, any pending trailing progress event
    is dropped so the UI's last frame is the terminal one
    rather than a stale "almost done" progress event."""
    await broadcaster.progress(
        job_run_id=1, current=1, total=10, message="step-1"
    )
    await broadcaster.progress(
        job_run_id=1, current=2, total=10, message="step-2"
    )
    # Both progress calls within the quiet window — first
    # emits, second is pending.
    await broadcaster.finished(
        job_run_id=1, status="success", items_processed=2
    )
    # Wait past the quiet window — the cancelled trailing
    # event must NOT fire.
    await asyncio.sleep(0.2)
    await broadcaster.aclose()

    # The terminal must be the last event.
    assert captured[-1]["eventType"] == "taskFinished"


@pytest.mark.asyncio
async def test_event_payload_shape(
    broadcaster: ProgressBroadcaster,
    captured: list[dict[str, Any]],
) -> None:
    """Sanity: the event dict carries the keys the WebSocket
    layer expects."""
    await broadcaster.progress(
        job_run_id=42, current=3, total=10, message="step-3"
    )
    await broadcaster.aclose()

    event = captured[0]
    assert event["eventType"] == "taskProgress"
    assert event["jobRunId"] == 42
    assert event["current"] == 3
    assert event["total"] == 10
    assert event["message"] == "step-3"
