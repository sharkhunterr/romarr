"""Graceful shutdown tests (T053-T055, FR-021, US6, SC-006)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from romarr.domain import Base
from romarr.tasks.execution.cancellation import CancellationRegistry
from romarr.tasks.models import Job, JobRun
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.shutdown import graceful_shutdown
from romarr.tasks.types import JobContext, JobResult, JobStatus


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def sm(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_job(sm: async_sessionmaker, job_id: str) -> None:
    async with sm() as session:
        session.add(
            Job(
                id=job_id,
                name=job_id,
                type="custom",
                schedule_interval_seconds=60,
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T053 — runners that finish within grace complete naturally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finishes_within_grace_period(
    sm: async_sessionmaker,
) -> None:
    """A runner that finishes inside the grace window
    completes naturally — no cancellation involved."""
    await _seed_job(sm, "FastJob")
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner(_ctx: JobContext) -> JobResult:
        started.set()
        await release.wait()
        return JobResult(status=JobStatus.SUCCESS)

    registry = CancellationRegistry()
    scheduler = SchedulerService(
        session_factory=sm,
        runners={"FastJob": runner},
        cancellation_registry=registry,
    )
    run_id = await scheduler.trigger("FastJob")
    await started.wait()

    # Schedule the release a moment before shutdown so the runner
    # finishes naturally within the grace window.
    async def release_soon() -> None:
        await asyncio.sleep(0.05)
        release.set()

    release_task = asyncio.create_task(release_soon())
    try:
        await graceful_shutdown(
            scheduler=scheduler,
            cancellation_registry=registry,
            grace_seconds=1.0,
            force_terminate_seconds=0.5,
        )
    finally:
        await release_task

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "success"
        assert run.cancellation_forced is False


# ---------------------------------------------------------------------------
# T054 — cooperative cancel after grace runs out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_after_grace(
    sm: async_sessionmaker,
) -> None:
    """A cooperative runner that doesn't finish within the
    grace window observes its cancellation_event and returns
    cancelled. ``cancellation_forced`` stays False — the
    runner cooperated."""
    await _seed_job(sm, "Cooperative")

    async def runner(ctx: JobContext) -> JobResult:
        await ctx.cancellation_event.wait()
        return JobResult(status=JobStatus.CANCELLED)

    registry = CancellationRegistry(force_terminate_after_seconds=0.5)
    scheduler = SchedulerService(
        session_factory=sm,
        runners={"Cooperative": runner},
        cancellation_registry=registry,
    )
    run_id = await scheduler.trigger("Cooperative")
    # Give the runner a tick to register.
    for _ in range(5):
        await asyncio.sleep(0)

    await graceful_shutdown(
        scheduler=scheduler,
        cancellation_registry=registry,
        grace_seconds=0.1,
        force_terminate_seconds=0.5,
    )

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancellation_forced is False


# ---------------------------------------------------------------------------
# T055 — force-terminate when the runner ignores the signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_terminate_when_runner_ignores_signal(
    sm: async_sessionmaker,
) -> None:
    """A runner that ignores ``cancellation_event`` is force-
    cancelled and the audit row records
    ``cancellation_forced=True`` (FR-021)."""
    await _seed_job(sm, "Stubborn")

    async def runner(_ctx: JobContext) -> JobResult:
        await asyncio.sleep(60.0)
        return JobResult(status=JobStatus.SUCCESS)

    registry = CancellationRegistry(force_terminate_after_seconds=0.2)
    scheduler = SchedulerService(
        session_factory=sm,
        runners={"Stubborn": runner},
        cancellation_registry=registry,
    )
    run_id = await scheduler.trigger("Stubborn")
    for _ in range(5):
        await asyncio.sleep(0)

    await graceful_shutdown(
        scheduler=scheduler,
        cancellation_registry=registry,
        grace_seconds=0.1,
        force_terminate_seconds=0.5,
    )

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancellation_forced is True


# ---------------------------------------------------------------------------
# Edge cases — empty inflight, no registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_with_no_inflight_runs(
    sm: async_sessionmaker,
) -> None:
    """Shutting down an idle scheduler returns cleanly."""
    scheduler = SchedulerService(session_factory=sm, runners={})
    await graceful_shutdown(
        scheduler=scheduler,
        cancellation_registry=None,
        grace_seconds=0.1,
        force_terminate_seconds=0.1,
    )
    # No assertion needed — the test passes if shutdown returns.


@pytest.mark.asyncio
async def test_shutdown_without_registry(
    sm: async_sessionmaker,
) -> None:
    """If no cancellation registry is wired, the shutdown
    handler skips the cooperative-cancel phase and goes
    straight to force-terminate after the grace window."""
    await _seed_job(sm, "NoRegistry")

    async def runner(_ctx: JobContext) -> JobResult:
        await asyncio.sleep(60.0)
        return JobResult(status=JobStatus.SUCCESS)

    scheduler = SchedulerService(
        session_factory=sm, runners={"NoRegistry": runner}
    )
    run_id = await scheduler.trigger("NoRegistry")
    for _ in range(5):
        await asyncio.sleep(0)

    await graceful_shutdown(
        scheduler=scheduler,
        cancellation_registry=None,
        grace_seconds=0.1,
        force_terminate_seconds=0.5,
    )

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        # Without a registry, no cooperative phase ran. The
        # task was force-cancelled. The audit row records
        # ``cancellation_forced=False`` because the cancellation
        # path goes through the scheduler's
        # ``CancelledError`` handler in ``_run_and_finalise``,
        # which sets ``cancellation_forced=True``.
        assert run.status == "cancelled"
        assert run.cancellation_forced is True
