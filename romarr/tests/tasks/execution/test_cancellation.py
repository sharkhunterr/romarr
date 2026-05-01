"""Cancellation tests (T035, T036, FR-021)."""

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
# T035 — cooperative cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooperative_cancel_emits_cancelled_status(
    sm: async_sessionmaker,
) -> None:
    """A runner that observes ``cancellation_event`` returns
    ``status=CANCELLED`` and the JobRun row reflects the
    terminal state without ``cancellation_forced=True``."""
    await _seed_job(sm, "Cooperative")

    cancellation_registry = CancellationRegistry(
        force_terminate_after_seconds=2.0,
    )

    async def cooperative_runner(ctx: JobContext) -> JobResult:
        # Wait for cancellation, return CANCELLED.
        await ctx.cancellation_event.wait()
        return JobResult(status=JobStatus.CANCELLED)

    service = SchedulerService(
        session_factory=sm,
        runners={"Cooperative": cooperative_runner},
        cancellation_registry=cancellation_registry,
    )
    try:
        run_id = await service.trigger("Cooperative")
        # Give the runner a chance to register.
        for _ in range(5):
            await asyncio.sleep(0)
        assert cancellation_registry.is_registered(run_id)

        cancelled = await cancellation_registry.cancel(run_id)
        assert cancelled is True
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        # Cooperative — not forced.
        assert run.cancellation_forced is False


# ---------------------------------------------------------------------------
# T036 — force-terminate after the cooperative window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_terminate_after_window(
    sm: async_sessionmaker,
) -> None:
    """A runner that ignores ``cancellation_event`` is force-
    terminated after the configured window, and the JobRun row
    records ``cancellation_forced=True``."""
    await _seed_job(sm, "Stubborn")

    cancellation_registry = CancellationRegistry(
        force_terminate_after_seconds=0.2,
    )

    async def stubborn_runner(_ctx: JobContext) -> JobResult:
        # Ignore the cancellation event.
        await asyncio.sleep(5.0)
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sm,
        runners={"Stubborn": stubborn_runner},
        cancellation_registry=cancellation_registry,
    )
    try:
        run_id = await service.trigger("Stubborn")
        for _ in range(5):
            await asyncio.sleep(0)
        cancelled = await cancellation_registry.cancel(run_id)
        assert cancelled is True
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancellation_forced is True


# ---------------------------------------------------------------------------
# Registry — basic shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_false() -> None:
    """No registered run for the id ⇒ cancel is a no-op
    returning False so the cancel-endpoint can surface 404."""
    registry = CancellationRegistry()
    assert await registry.cancel(999999) is False


@pytest.mark.asyncio
async def test_is_registered_reflects_current_state() -> None:
    registry = CancellationRegistry()
    assert registry.is_registered(1) is False

    event = asyncio.Event()

    async def task_body() -> None:
        await event.wait()

    task = asyncio.create_task(task_body())
    try:
        await registry.register(
            job_run_id=1,
            cancellation_event=event,
            task=task,
        )
        assert registry.is_registered(1) is True
    finally:
        event.set()
        await task
    # Done callback drops the entry.
    await asyncio.sleep(0)
    assert registry.is_registered(1) is False


@pytest.mark.asyncio
async def test_cancel_all_signals_every_registered_run() -> None:
    """Used by lifespan shutdown to drain in-flight runs."""
    registry = CancellationRegistry(force_terminate_after_seconds=0.2)

    async def cooperative(event: asyncio.Event) -> None:
        await event.wait()

    events = [asyncio.Event() for _ in range(3)]
    tasks = [asyncio.create_task(cooperative(e)) for e in events]
    for i, (event, task) in enumerate(zip(events, tasks, strict=True)):
        await registry.register(
            job_run_id=i + 1,
            cancellation_event=event,
            task=task,
        )

    await registry.cancel_all()
    # All tasks should have been signalled and completed.
    for task in tasks:
        assert task.done()
