"""Cancellation registry + force-terminate helper (T042, FR-021).

Each in-flight runner exposes its
``JobContext.cancellation_event``. When the operator cancels
a run via ``DELETE /api/v3/job/{id}/run/{run_id}`` (spec 013),
or when the lifespan handler is shutting down, the
:class:`CancellationRegistry` looks up the right
:class:`asyncio.Event` and signals it.

Cooperative runners ``await cancellation_event.wait()`` (or
periodically check ``cancellation_event.is_set()``) and return
``JobResult(status=CANCELLED)`` cleanly. Stubborn runners that
ignore the signal are force-terminated after 5 seconds via
``asyncio.Task.cancel()`` plus a timeout-bounded await — the
audit row records ``cancellation_forced=True`` so the operator
sees the escalation.

The registry is single-process: each replica has its own.
Cancellation across replicas isn't part of the MVP — the
operator UI reports which replica is running which job, and
the cancel endpoint targets a specific replica.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


# FR-021: cooperative cancel waits up to 5 s for the runner to
# observe its event before force-terminating.
DEFAULT_FORCE_TERMINATE_AFTER_SECONDS: float = 5.0


@dataclass
class _RegisteredRun:
    """The two handles per in-flight run."""

    cancellation_event: asyncio.Event
    task: asyncio.Task[None]


class CancellationRegistry:
    """Per-process map of ``job_run_id -> (event, task)``.

    The scheduler registers a run when it spawns the runner
    task and unregisters when the task completes. The cancel
    endpoint looks up the entry by ``job_run_id`` and calls
    :meth:`cancel`.
    """

    def __init__(
        self,
        *,
        force_terminate_after_seconds: float = DEFAULT_FORCE_TERMINATE_AFTER_SECONDS,
    ) -> None:
        self._force_terminate_after_seconds = force_terminate_after_seconds
        self._runs: dict[int, _RegisteredRun] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        job_run_id: int,
        cancellation_event: asyncio.Event,
        task: asyncio.Task[None],
    ) -> None:
        """Add a run to the registry. Auto-unregisters when the
        task completes via ``add_done_callback``."""
        async with self._lock:
            self._runs[job_run_id] = _RegisteredRun(
                cancellation_event=cancellation_event,
                task=task,
            )

        def _drop(_t: asyncio.Task[None], rid: int = job_run_id) -> None:
            self._runs.pop(rid, None)

        task.add_done_callback(_drop)

    async def cancel(self, job_run_id: int) -> bool:
        """Signal cancellation for ``job_run_id``. Returns True
        if a run was found and the cooperative phase has been
        triggered (or completed). False if the run isn't
        registered (already finished, never started, wrong
        replica).

        The caller is the cancel-endpoint coroutine — it's the
        right place to await the cooperative grace period and
        force-terminate if the runner doesn't bail. Returns
        once the task has reached a terminal state.
        """
        async with self._lock:
            entry = self._runs.get(job_run_id)
        if entry is None:
            return False

        # Phase 1 — signal the cooperative event. A runner that
        # ``awaits cancellation_event.wait()`` returns now.
        entry.cancellation_event.set()

        # Phase 2 — wait up to N seconds for the task to finish
        # cooperatively.
        try:
            await asyncio.wait_for(
                asyncio.shield(entry.task),
                timeout=self._force_terminate_after_seconds,
            )
            return True
        except TimeoutError:
            pass

        # Phase 3 — force-terminate. The runner ignored the
        # cooperative signal; we cancel the task directly. The
        # scheduler's ``_run_and_finalise`` catches CancelledError
        # and writes ``cancellation_forced=True`` on the audit row.
        _logger.warning(
            "cancellation force-terminated job_run_id=%s after %.1fs",
            job_run_id,
            self._force_terminate_after_seconds,
        )
        entry.task.cancel()
        with contextlib.suppress(BaseException):
            await entry.task
        return True

    def is_registered(self, job_run_id: int) -> bool:
        """Cheap check the cancel-endpoint can use to surface
        404 vs the no-op cancel-twice case."""
        return job_run_id in self._runs

    async def cancel_all(self) -> None:
        """Used by the lifespan shutdown handler to cancel
        every in-flight run."""
        async with self._lock:
            run_ids = list(self._runs.keys())
        for run_id in run_ids:
            await self.cancel(run_id)


__all__ = [
    "DEFAULT_FORCE_TERMINATE_AFTER_SECONDS",
    "CancellationRegistry",
]
