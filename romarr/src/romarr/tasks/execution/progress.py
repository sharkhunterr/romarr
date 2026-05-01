"""Progress event throttling (T041, FR-023, SC-008).

Runners emit ``progress_callback(current, total, message)``
calls liberally — once per processed item is common. The
WebSocket / SSE channel that surfaces these to the frontend
can't sustain that rate without saturating the operator's
browser. The throttle clamps to ≤ 10 events/sec per
``job_run_id``: the first event in a 100 ms quiet window
fires immediately; any subsequent events within that window
collapse to ONE trailing event with the latest values.

Final ``taskFinished`` events bypass the throttle entirely so
the operator's UI always sees the terminal state — losing the
final event (status=success / failed / cancelled) would leave
a "running" indicator stuck.

The broadcaster is transport-agnostic: it accepts an injected
``emit`` callable that the lifespan wires to the WebSocket
broadcaster (spec 013) or to a no-op for tests. The throttle
itself is single-process; if Romarr ever runs multi-replica,
each replica throttles independently — the per-runId scope
keeps them from stepping on each other.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)


# 100 ms quiet window → max 10 events/sec per runId.
_THROTTLE_WINDOW_SECONDS: float = 0.1


@dataclass
class _PerRunState:
    """Throttle state for one in-flight ``job_run_id``."""

    last_emitted_at: float = 0.0
    pending_event: dict[str, Any] | None = None
    pending_task: asyncio.Task[None] | None = None


type EmitCallable = "Callable[[dict[str, Any]], Awaitable[None]]"


class ProgressBroadcaster:
    """Per-process throttle for progress events.

    ``emit`` is the transport-agnostic sink — production wiring
    (spec 013) hands it the WebSocket broadcaster; tests pass
    a recording mock. Each ``progress(...)`` call computes the
    elapsed time since the last emission for the same
    ``job_run_id``: if ≥ 100 ms elapsed, emit immediately and
    record. Otherwise, schedule a trailing emission at the end
    of the quiet window with the latest values, replacing any
    earlier pending trailing emission.

    ``finished(...)`` always emits immediately, bypassing the
    throttle and clearing any pending trailing event so the
    UI doesn't see a stale "almost done" frame after the
    terminal one.
    """

    def __init__(
        self,
        *,
        emit: EmitCallable,
        window_seconds: float = _THROTTLE_WINDOW_SECONDS,
    ) -> None:
        self._emit = emit
        self._window_seconds = window_seconds
        self._states: dict[int, _PerRunState] = {}
        self._lock = asyncio.Lock()

    async def progress(
        self,
        *,
        job_run_id: int,
        current: int,
        total: int,
        message: str = "",
    ) -> None:
        """Record a progress tick. May or may not emit
        immediately, depending on the throttle window."""
        event = self._build_event(
            job_run_id=job_run_id,
            current=current,
            total=total,
            message=message,
            event_type="taskProgress",
        )

        async with self._lock:
            state = self._states.setdefault(job_run_id, _PerRunState())
            now = time.monotonic()
            elapsed = now - state.last_emitted_at

            if elapsed >= self._window_seconds:
                state.last_emitted_at = now
                # Drop any pending trailing event — we're emitting
                # a fresh one right now, which carries the latest
                # values anyway.
                if state.pending_task is not None and not state.pending_task.done():
                    state.pending_task.cancel()
                state.pending_event = None
                state.pending_task = None
                await self._emit(event)
                return

            # Within the quiet window — schedule (or refresh) a
            # trailing emission with the latest values.
            state.pending_event = event
            if state.pending_task is None or state.pending_task.done():
                wait_for = self._window_seconds - elapsed
                state.pending_task = asyncio.create_task(
                    self._flush_after(job_run_id, wait_for),
                    name=f"progress-flush-{job_run_id}",
                )

    async def finished(
        self,
        *,
        job_run_id: int,
        status: str,
        items_processed: int = 0,
        message: str = "",
    ) -> None:
        """Terminal event — always emits immediately, bypassing
        the throttle. Clears any pending trailing event so the
        UI's last frame is the terminal one."""
        event = {
            "eventType": "taskFinished",
            "jobRunId": job_run_id,
            "status": status,
            "itemsProcessed": items_processed,
            "message": message,
        }
        async with self._lock:
            state = self._states.get(job_run_id)
            if state is not None:
                if state.pending_task is not None and not state.pending_task.done():
                    state.pending_task.cancel()
                state.pending_event = None
                state.pending_task = None
                state.last_emitted_at = time.monotonic()
            await self._emit(event)

    async def aclose(self) -> None:
        """Cancel any pending trailing emissions. Useful for
        lifespan shutdown."""
        async with self._lock:
            for state in self._states.values():
                task = state.pending_task
                if task is not None and not task.done():
                    task.cancel()

    # ------------------------------------------------------------------

    async def _flush_after(self, job_run_id: int, wait_for: float) -> None:
        try:
            await asyncio.sleep(wait_for)
        except asyncio.CancelledError:
            return
        async with self._lock:
            state = self._states.get(job_run_id)
            if state is None or state.pending_event is None:
                return
            event = state.pending_event
            state.pending_event = None
            state.pending_task = None
            state.last_emitted_at = time.monotonic()
        await self._emit(event)

    @staticmethod
    def _build_event(
        *,
        job_run_id: int,
        current: int,
        total: int,
        message: str,
        event_type: str,
    ) -> dict[str, Any]:
        return {
            "eventType": event_type,
            "jobRunId": job_run_id,
            "current": current,
            "total": total,
            "message": message,
        }


__all__ = ["ProgressBroadcaster"]
