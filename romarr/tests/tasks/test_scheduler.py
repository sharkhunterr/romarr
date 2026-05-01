"""SchedulerService tests (T018-T022, FR-006/FR-009/FR-012/FR-026, SC-003/SC-004/SC-007)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixtures + helpers
#
# The scheduler spawns runner tasks that open their own sessions
# from the shared sessionmaker. With bare ``:memory:`` SQLite each
# connection gets a fresh empty DB, so the runner's writes don't
# survive to the polling loop. ``cache=shared`` plus a per-test
# unique name keeps every connection pointing at the same in-memory
# DB while keeping tests isolated from each other.
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from romarr.domain import Base
from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    UnknownJob,
)
from romarr.tasks.models import Job, JobRun
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.types import (
    JobContext,
    JobResult,
    JobStatus,
    TriggerKind,
)


@pytest_asyncio.fixture
async def shared_engine() -> AsyncIterator[AsyncEngine]:
    """Per-test in-memory SQLite with one shared connection.

    The scheduler spawns runner tasks that open their own
    sessions. Without a single shared connection, each session
    on bare ``:memory:`` sees a fresh empty DB and the runner's
    writes are invisible to the polling loop. The shared-cache
    URL form has flaky behaviour across test runs in the same
    process. StaticPool forces every session to reuse the same
    underlying aiosqlite connection — fast, isolated per test,
    and correct for this multi-session profile.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(
    shared_engine: AsyncEngine,
) -> async_sessionmaker:
    return async_sessionmaker(shared_engine, expire_on_commit=False)


async def _seed_job(
    sessionmaker: async_sessionmaker,
    *,
    job_id: str,
    job_type: str = "custom",
    interval_seconds: int | None = 60,
    cron: str | None = None,
    enabled: bool = True,
    max_concurrent: int = 1,
) -> None:
    async with sessionmaker() as session:
        session.add(
            Job(
                id=job_id,
                name=job_id,
                type=job_type,
                schedule_cron=cron,
                schedule_interval_seconds=interval_seconds,
                enabled=enabled,
                max_concurrent_instances=max_concurrent,
            )
        )
        await session.commit()


async def _count_runs(
    sessionmaker: async_sessionmaker, job_id: str
) -> int:
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(JobRun).where(JobRun.job_id == job_id)
            )
        ).scalars().all()
        return len(rows)


# ---------------------------------------------------------------------------
# T018 — bootstrap registers enabled jobs only (FR-006)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_registers_enabled_only(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(sessionmaker, job_id="A", interval_seconds=60)
    await _seed_job(sessionmaker, job_id="B", interval_seconds=120)
    await _seed_job(sessionmaker, job_id="C", cron="0 * * * *")
    await _seed_job(
        sessionmaker, job_id="D", interval_seconds=60, enabled=False
    )

    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    await service.start()
    try:
        registered = {job.id for job in service._scheduler.get_jobs()}
        assert registered == {"A", "B", "C"}
    finally:
        await service.stop()


# ---------------------------------------------------------------------------
# T019 — misfire grace 60 min coalesces (SC-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_misfire_grace_coalesces(
    sessionmaker: async_sessionmaker,
) -> None:
    """SC-004: ``coalesce=True`` + ``misfire_grace_time=3600``
    means an 8 h gap fires the most recent missed cycle once,
    not once per missed cycle. We don't run real wall-clock
    here; we assert the APScheduler job carries the documented
    config so future regressions trip on the cap rather than
    in production."""
    await _seed_job(
        sessionmaker, job_id="MisfireJob", interval_seconds=60
    )
    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    await service.start()
    try:
        job = service._scheduler.get_job("MisfireJob")
        assert job is not None
        assert job.misfire_grace_time == 3600
        assert job.coalesce is True
    finally:
        await service.stop()


# ---------------------------------------------------------------------------
# T020 — concurrent trigger raises JobAlreadyRunning (FR-012, SC-003)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_trigger_raises_when_at_cap(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(
        sessionmaker,
        job_id="OneAtATime",
        interval_seconds=60,
        max_concurrent=1,
    )

    blocked = asyncio.Event()
    release = asyncio.Event()

    async def slow_runner(_ctx: JobContext) -> JobResult:
        blocked.set()
        await release.wait()
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sessionmaker,
        runners={"OneAtATime": slow_runner},
    )
    try:
        run_id_1 = await service.trigger("OneAtATime")
        await blocked.wait()  # the runner is now in-flight

        # Second trigger should raise — the runner is still in-flight.
        with pytest.raises(JobAlreadyRunning):
            await service.trigger("OneAtATime")

        release.set()
        # Wait for the runner to finish, then a fresh trigger
        # should succeed.
        await service.await_run(run_id_1)
        run_id_2 = await service.trigger("OneAtATime")
        assert run_id_2 != run_id_1
    finally:
        release.set()
        await service.stop()


# ---------------------------------------------------------------------------
# T021 — max_concurrent_instances = 2 honored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_concurrent_2(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(
        sessionmaker,
        job_id="TwoAtATime",
        interval_seconds=60,
        max_concurrent=2,
    )

    blocked: list[asyncio.Event] = [asyncio.Event() for _ in range(3)]
    release: list[asyncio.Event] = [asyncio.Event() for _ in range(3)]
    counter = {"value": 0}
    counter_lock = asyncio.Lock()

    async def slow_runner(_ctx: JobContext) -> JobResult:
        async with counter_lock:
            idx = counter["value"]
            counter["value"] += 1
        blocked[idx].set()
        await release[idx].wait()
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sessionmaker,
        runners={"TwoAtATime": slow_runner},
    )
    try:
        first_id = await service.trigger("TwoAtATime")
        second_id = await service.trigger("TwoAtATime")
        await blocked[0].wait()
        await blocked[1].wait()

        # Third trigger should raise — at cap of 2.
        with pytest.raises(JobAlreadyRunning):
            await service.trigger("TwoAtATime")

        # Release one slot — third trigger should now succeed.
        release[0].set()
        await service.await_run(first_id)
        third_id = await service.trigger("TwoAtATime")
        assert third_id != first_id
        assert third_id != second_id
    finally:
        for ev in release:
            ev.set()
        await service.stop()


# ---------------------------------------------------------------------------
# T022 — reschedule applies without restart (FR-026, SC-007)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_takes_effect(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(
        sessionmaker, job_id="Reschedulable", interval_seconds=60
    )
    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    await service.start()
    try:
        await service.reschedule_job(
            "Reschedulable", interval_seconds=900
        )
        # The Job row reflects the new cadence.
        async with sessionmaker() as session:
            job = await session.get(Job, "Reschedulable")
            assert job is not None
            assert job.schedule_interval_seconds == 900

        # Switch to cron — same code path with the alternate field.
        await service.reschedule_job(
            "Reschedulable", cron="0 */6 * * *"
        )
        async with sessionmaker() as session:
            job = await session.get(Job, "Reschedulable")
            assert job is not None
            assert job.schedule_cron == "0 */6 * * *"
            assert job.schedule_interval_seconds is None
    finally:
        await service.stop()


# ---------------------------------------------------------------------------
# Edge cases — disabled / unknown / event-driven
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_job_raises(
    sessionmaker: async_sessionmaker,
) -> None:
    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    with pytest.raises(UnknownJob):
        await service.trigger("DoesNotExist")


@pytest.mark.asyncio
async def test_disabled_job_raises_unless_forced(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(
        sessionmaker,
        job_id="Disabled",
        interval_seconds=60,
        enabled=False,
    )
    runner_calls: list[JobContext] = []

    async def runner(ctx: JobContext) -> JobResult:
        runner_calls.append(ctx)
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sessionmaker, runners={"Disabled": runner}
    )
    with pytest.raises(JobDisabled):
        await service.trigger("Disabled")
    assert runner_calls == []

    # ``force=True`` bypasses the disabled gate.
    run_id = await service.trigger("Disabled", force=True)
    assert run_id > 0
    await _wait_for_run_terminal(sessionmaker, run_id)
    assert len(runner_calls) == 1


@pytest.mark.asyncio
async def test_event_driven_job_skipped_in_bootstrap(
    sessionmaker: async_sessionmaker,
) -> None:
    """``AutoCheckAdded`` has no schedule — bootstrap must skip
    rather than crash."""
    async with sessionmaker() as session:
        session.add(
            Job(
                id="AutoCheckAdded",
                name="auto",
                type="auto_check_added",
                schedule_cron=None,
                schedule_interval_seconds=None,
                enabled=True,
            )
        )
        await session.commit()

    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    await service.start()
    try:
        registered = {job.id for job in service._scheduler.get_jobs()}
        assert "AutoCheckAdded" not in registered
    finally:
        await service.stop()


# ---------------------------------------------------------------------------
# Audit — finalise updates job_run + job rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_success_marks_job_run_success(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(sessionmaker, job_id="Audited", interval_seconds=60)

    async def runner(_ctx: JobContext) -> JobResult:
        return JobResult(
            status=JobStatus.SUCCESS,
            items_processed=42,
            summary={"processed": 42},
        )

    service = SchedulerService(
        session_factory=sessionmaker, runners={"Audited": runner}
    )
    try:
        run_id = await service.trigger("Audited")
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sessionmaker() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "success"
        assert run.items_processed == 42
        assert run.duration_ms is not None
        assert run.duration_ms >= 0

        job = await session.get(Job, "Audited")
        assert job is not None
        assert job.last_run_status == "success"
        assert job.last_run_at is not None
        assert job.last_error is None


@pytest.mark.asyncio
async def test_runner_exception_marks_job_run_failed(
    sessionmaker: async_sessionmaker,
) -> None:
    await _seed_job(sessionmaker, job_id="Buggy", interval_seconds=60)

    async def runner(_ctx: JobContext) -> JobResult:
        raise RuntimeError("oops")

    service = SchedulerService(
        session_factory=sessionmaker, runners={"Buggy": runner}
    )
    try:
        run_id = await service.trigger("Buggy")
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sessionmaker() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert "RuntimeError" in (run.error_message or "")

        job = await session.get(Job, "Buggy")
        assert job is not None
        assert job.last_run_status == "failed"


@pytest.mark.asyncio
async def test_no_runner_registered_marks_failed(
    sessionmaker: async_sessionmaker,
) -> None:
    """Triggering a job whose runner isn't in the registry
    surfaces as a failed job_run (rather than a hung run)."""
    await _seed_job(sessionmaker, job_id="Orphan", interval_seconds=60)
    service = SchedulerService(
        session_factory=sessionmaker, runners={}
    )
    try:
        run_id = await service.trigger("Orphan")
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sessionmaker() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert "no runner" in (run.error_message or "").lower()


# ---------------------------------------------------------------------------
# Triggered-by attribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_records_triggered_by(
    sessionmaker: async_sessionmaker,
) -> None:
    """User attribution is captured. We seed a real user so the
    FK constraint passes — the SET NULL behavior on user delete
    is exercised in spec 010's auth tests."""
    from romarr.auth.models import User

    await _seed_job(sessionmaker, job_id="Attributed", interval_seconds=60)
    async with sessionmaker() as session:
        session.add(
            User(
                username="trigger-test",
                role="admin",
                is_active=True,
                hashed_password="x",
            )
        )
        await session.commit()
        user = (
            await session.execute(
                select(User).where(User.username == "trigger-test")
            )
        ).scalar_one()
        user_id = user.id

    async def runner(_ctx: JobContext) -> JobResult:
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sessionmaker, runners={"Attributed": runner}
    )
    try:
        run_id = await service.trigger(
            "Attributed",
            triggered_by=TriggerKind.COMMAND,
            triggered_by_user_id=user_id,
        )
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sessionmaker() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.triggered_by == "command"
        assert run.triggered_by_user_id == user_id


# ---------------------------------------------------------------------------
# Internals helpers


async def _wait_for_run_terminal(
    sessionmaker: async_sessionmaker,
    run_id: int,
    *,
    timeout: float = 30.0,
) -> None:
    """Poll the JobRun row until it reaches a terminal status.

    Yields a few extra event-loop ticks after observing
    terminal so the runner task's ``add_done_callback`` has
    fired — otherwise a follow-up trigger could see the task
    still in the inflight set even though its row is already
    persisted.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with sessionmaker() as session:
            run = await session.get(JobRun, run_id)
            if run is not None and run.status != "running":
                # Yield extra ticks so the task's done callback
                # fires and the scheduler's inflight bookkeeping
                # catches up with the persisted state.
                for _ in range(3):
                    await asyncio.sleep(0)
                return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"job_run {run_id} did not reach terminal status within {timeout}s"
    )


# Sanity: confirm the public types are importable.
def test_public_types_importable() -> None:
    assert SchedulerService is not None
    assert JobResult is not None
    _: dict[str, Any] = {}
    _ = _
