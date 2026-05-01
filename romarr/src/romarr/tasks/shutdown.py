"""Graceful shutdown of the tasks subsystem (T056, FR-021, US6).

The lifespan handler calls :func:`graceful_shutdown` when the
container receives SIGTERM (Docker / Kubernetes / systemd).
The protocol:

  1. **Stop the scheduler** (no new APScheduler ticks; in-flight
     runs continue).
  2. **Wait up to ``grace_seconds`` (default 30 s)** for the
     in-flight runs to finish naturally. Most runners — backup,
     RSS sync, the typical search round — complete inside that
     window.
  3. **Signal every remaining run's** ``cancellation_event`` so
     cooperative runners exit cleanly. They get
     ``force_terminate_seconds`` (default 5 s) to do so.
  4. **Force-cancel** the asyncio tasks of any runners still
     hanging — the audit row records
     ``cancellation_forced=True`` (FR-021).

The function is total: every code path reaches the same
"return when the scheduler is fully stopped" state, even if
intermediate steps raise. Lifespan can't safely retry shutdown,
so we don't propagate.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.tasks.execution.cancellation import CancellationRegistry
    from romarr.tasks.scheduler import SchedulerService

_logger = logging.getLogger(__name__)


DEFAULT_GRACE_SECONDS: float = 30.0
"""How long the shutdown handler waits for in-flight runs to
finish naturally before signalling cancellation. SC-006 mandates
30 s for the steady-state."""


DEFAULT_FORCE_TERMINATE_SECONDS: float = 5.0
"""Additional grace period after cancellation signal, before
force-cancelling the asyncio tasks (FR-021)."""


async def graceful_shutdown(
    *,
    scheduler: SchedulerService,
    cancellation_registry: CancellationRegistry | None = None,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    force_terminate_seconds: float = DEFAULT_FORCE_TERMINATE_SECONDS,
) -> None:
    """Run the four-step shutdown protocol.

    Always returns; never raises. Failures inside individual
    steps are logged and swallowed so the lifespan teardown
    can complete.
    """
    _logger.info(
        "tasks shutdown: starting graceful shutdown "
        "(grace=%.1fs, force_terminate=%.1fs)",
        grace_seconds,
        force_terminate_seconds,
    )

    # Phase 1: stop accepting new triggers. APScheduler's
    # ``shutdown(wait=False)`` returns immediately — we want
    # control of the wait policy for in-flight runs ourselves.
    try:
        scheduler._scheduler.shutdown(wait=False)
        scheduler._started = False
    except Exception:
        _logger.exception("scheduler shutdown raised — continuing")

    # Phase 2: wait for inflight runs to finish naturally.
    inflight_tasks = _collect_inflight_tasks(scheduler)
    if inflight_tasks:
        _logger.info(
            "tasks shutdown: awaiting %d in-flight run(s) for up to %.1fs",
            len(inflight_tasks),
            grace_seconds,
        )
        await _wait_for_tasks(inflight_tasks, timeout=grace_seconds)

    # Phase 3: cancellation signal on whatever's still running.
    still_running = _filter_still_running(inflight_tasks)
    if still_running and cancellation_registry is not None:
        _logger.info(
            "tasks shutdown: signalling cancellation on %d remaining run(s)",
            len(still_running),
        )
        await cancellation_registry.cancel_all()

    # Phase 4: force-cancel any tasks that ignored the signal.
    still_running = _filter_still_running(inflight_tasks)
    if still_running:
        _logger.warning(
            "tasks shutdown: force-cancelling %d run(s) that ignored "
            "the cancellation signal",
            len(still_running),
        )
        for task in still_running:
            task.cancel()
        await _wait_for_tasks(
            still_running, timeout=force_terminate_seconds
        )

    _logger.info("tasks shutdown: complete")


# ---------------------------------------------------------------------------
# Internals


def _collect_inflight_tasks(
    scheduler: SchedulerService,
) -> list[asyncio.Task[None]]:
    """Snapshot the scheduler's inflight tasks. We snapshot
    rather than iterate live because the dict mutates as
    runners finish."""
    tasks: list[asyncio.Task[None]] = []
    for task_set in scheduler._inflight.values():
        tasks.extend(task_set)
    return tasks


def _filter_still_running(
    tasks: list[asyncio.Task[None]],
) -> list[asyncio.Task[None]]:
    return [task for task in tasks if not task.done()]


async def _wait_for_tasks(
    tasks: list[asyncio.Task[None]],
    *,
    timeout: float,
) -> None:
    """``asyncio.wait`` with a timeout. Errors and cancellations
    are swallowed — we only care about completion state."""
    if not tasks:
        return
    try:
        await asyncio.wait(tasks, timeout=timeout)
    except Exception:
        _logger.exception(
            "tasks shutdown: error while awaiting tasks — continuing"
        )


__all__ = [
    "DEFAULT_FORCE_TERMINATE_SECONDS",
    "DEFAULT_GRACE_SECONDS",
    "graceful_shutdown",
]
