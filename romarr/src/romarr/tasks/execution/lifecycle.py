"""JobRun lifecycle helpers (T040, FR-013).

Each helper writes one row state-transition to the
``job_run`` table:

  * :func:`start_run` — INSERT a row with ``status='running'``
    and the trigger attribution columns. Returns the new
    ``job_run.id``.
  * :func:`finish_run` — UPDATE the running row to a terminal
    status carrying ``items_processed``, ``output_summary``,
    ``finished_at``, ``duration_ms``. Mirrors the terminal
    status onto the parent ``Job`` row's ``last_run_*`` audit
    columns so the operator's UI gets an at-a-glance view.
  * :func:`fail_run` — terminal status ``failed`` with a
    structured ``error_message``.
  * :func:`cancel_run` — terminal status ``cancelled`` with
    optional ``cancellation_forced`` flag for the FR-021
    force-terminate path.

These helpers were inlined into
:mod:`romarr.tasks.scheduler`'s ``trigger`` /
``_finalise`` paths in slice 11; this slice extracts them so
runner adapters can call them directly (e.g. for partial-
success outcomes where the runner wants to write
``items_processed`` without going through the scheduler's
catch-all). The scheduler now delegates to these helpers,
keeping its own surface focused on dispatch + concurrency.

The helpers are session-scoped — the caller is responsible
for opening the session and committing. This keeps the
helpers pure (no I/O beyond the SQL) and lets the scheduler
batch the start_run + commit + dispatch into one transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from romarr.tasks.models import Job, JobRun
from romarr.tasks.types import JobStatus, TriggerKind

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def start_run(
    session: AsyncSession,
    *,
    job_id: str,
    triggered_by: TriggerKind,
    triggered_by_user_id: int | None = None,
) -> JobRun:
    """INSERT a fresh ``running`` row. Returns the persisted
    row so callers can capture the auto-incremented id."""
    run = JobRun(
        job_id=job_id,
        started_at=datetime.now(UTC),
        status=JobStatus.RUNNING.value,
        triggered_by=triggered_by.value,
        triggered_by_user_id=triggered_by_user_id,
    )
    session.add(run)
    await session.flush()  # populate run.id without commit
    await session.refresh(run)
    return run


async def finish_run(
    session: AsyncSession,
    *,
    job_run_id: int,
    status: JobStatus,
    items_processed: int = 0,
    output_summary: dict[str, Any] | None = None,
    error_message: str | None = None,
    cancellation_forced: bool = False,
) -> JobRun | None:
    """Transition the row to a terminal status. Returns the
    updated :class:`JobRun` (or ``None`` if the row vanished
    mid-run — defensive)."""
    run = await session.get(JobRun, job_run_id)
    if run is None:
        return None

    now = datetime.now(UTC)
    run.finished_at = now
    run.status = status.value
    run.error_message = error_message
    run.items_processed = items_processed
    run.output_summary = output_summary
    run.cancellation_forced = cancellation_forced

    # SQLite via aiosqlite drops tzinfo on round-trip, so
    # ``started_at`` may come back naive even when written with
    # UTC. Normalise so the subtraction works on every backend.
    started = run.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    run.duration_ms = int((now - started).total_seconds() * 1000)

    # Mirror the terminal status onto the parent Job row.
    job = await session.get(Job, run.job_id)
    if job is not None:
        job.last_run_at = now
        job.last_run_duration_ms = run.duration_ms
        job.last_run_status = status.value
        job.last_error = error_message

    return run


async def fail_run(
    session: AsyncSession,
    *,
    job_run_id: int,
    error_message: str,
) -> JobRun | None:
    """Convenience wrapper — failed terminal status with the
    structured error message."""
    return await finish_run(
        session,
        job_run_id=job_run_id,
        status=JobStatus.FAILED,
        error_message=error_message,
    )


async def cancel_run(
    session: AsyncSession,
    *,
    job_run_id: int,
    forced: bool = False,
) -> JobRun | None:
    """Cancellation terminal status. ``forced=True`` records
    the FR-021 force-terminate flag."""
    return await finish_run(
        session,
        job_run_id=job_run_id,
        status=JobStatus.CANCELLED,
        cancellation_forced=forced,
    )


__all__ = [
    "cancel_run",
    "fail_run",
    "finish_run",
    "start_run",
]
