"""Auto-pause tests (T037, T038, T039, FR-018, SC-005)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from romarr.domain import Base
from romarr.notifications.types import (
    ComponentCategory,
    HealthSnapshot,
    HealthStatus,
)
from romarr.tasks.execution.auto_pause import PAUSING_STATUSES, AutoPause
from romarr.tasks.models import Job, JobRun
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.types import JobContext, JobResult, JobStatus, TriggerKind


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


def _snapshot(status: HealthStatus) -> HealthSnapshot:
    return HealthSnapshot(
        overall_status=status,
        by_category={ComponentCategory.DB: []},
        refreshed_at=datetime.now(UTC),
    )


def _provider(status: HealthStatus):
    async def provider() -> HealthSnapshot:
        return _snapshot(status)

    return provider


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
# AutoPause predicate — unit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_pause_paused_when_health_error() -> None:
    pause = AutoPause(snapshot_provider=_provider(HealthStatus.ERROR))
    assert await pause.is_paused() is True


@pytest.mark.asyncio
async def test_auto_pause_not_paused_when_health_ok() -> None:
    pause = AutoPause(snapshot_provider=_provider(HealthStatus.OK))
    assert await pause.is_paused() is False


@pytest.mark.asyncio
async def test_auto_pause_not_paused_when_health_warning() -> None:
    """Warnings are informational — RSS sync still fires."""
    pause = AutoPause(snapshot_provider=_provider(HealthStatus.WARNING))
    assert await pause.is_paused() is False


@pytest.mark.asyncio
async def test_auto_pause_soft_gate_on_provider_error() -> None:
    """A broken health system shouldn't paralyse the scheduler.
    The gate fails open."""

    async def broken() -> HealthSnapshot:
        raise RuntimeError("snapshot provider exploded")

    pause = AutoPause(snapshot_provider=broken)
    assert await pause.is_paused() is False


# ---------------------------------------------------------------------------
# T037 — scheduled tick suppressed when paused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_trigger_suppressed_when_paused(
    sm: async_sessionmaker,
) -> None:
    await _seed_job(sm, "PausedJob")
    runner_calls: list[str] = []

    async def runner(_ctx: JobContext) -> JobResult:
        runner_calls.append("ran")
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sm,
        runners={"PausedJob": runner},
        auto_pause=AutoPause(
            snapshot_provider=_provider(HealthStatus.ERROR),
        ),
    )
    try:
        result = await service.trigger(
            "PausedJob",
            triggered_by=TriggerKind.SCHEDULED,
        )
        # Sentinel value: -1 indicates "auto-paused, didn't run".
        assert result == -1
        assert runner_calls == []
    finally:
        await service.stop()

    # No JobRun row was created — the scheduler short-circuited
    # before start_run.
    async with sm() as session:
        rows = (
            await session.execute(JobRun.__table__.select())
        ).fetchall()
        assert rows == []


# ---------------------------------------------------------------------------
# T038 — manual force=True bypasses auto-pause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_overrides_pause(
    sm: async_sessionmaker,
) -> None:
    await _seed_job(sm, "ForceMe")
    runner_calls: list[str] = []

    async def runner(_ctx: JobContext) -> JobResult:
        runner_calls.append("ran")
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sm,
        runners={"ForceMe": runner},
        auto_pause=AutoPause(
            snapshot_provider=_provider(HealthStatus.ERROR),
        ),
    )
    try:
        # Manual triggers always fire (US5.2).
        run_id = await service.trigger(
            "ForceMe",
            triggered_by=TriggerKind.MANUAL,
        )
        assert run_id > 0
        await service.await_run(run_id)
        assert runner_calls == ["ran"]
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_force_true_bypasses_even_for_scheduled_kind(
    sm: async_sessionmaker,
) -> None:
    """Defensive: ``force=True`` on a SCHEDULED-kind trigger
    (rare but documented) bypasses the gate too."""
    await _seed_job(sm, "ForceScheduled")
    runner_calls: list[str] = []

    async def runner(_ctx: JobContext) -> JobResult:
        runner_calls.append("ran")
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sm,
        runners={"ForceScheduled": runner},
        auto_pause=AutoPause(
            snapshot_provider=_provider(HealthStatus.ERROR),
        ),
    )
    try:
        run_id = await service.trigger(
            "ForceScheduled",
            triggered_by=TriggerKind.SCHEDULED,
            force=True,
        )
        assert run_id > 0
        await service.await_run(run_id)
        assert runner_calls == ["ran"]
    finally:
        await service.stop()


# ---------------------------------------------------------------------------
# T039 — in-flight runs continue when health degrades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inflight_run_continues_when_health_degrades(
    sm: async_sessionmaker,
) -> None:
    """Auto-pause only suppresses NEW scheduled triggers (US5.3).
    A run that was already in-flight when health degraded
    completes normally."""
    await _seed_job(sm, "Inflight")

    snapshot_state = {"value": HealthStatus.OK}

    async def provider() -> HealthSnapshot:
        return _snapshot(snapshot_state["value"])

    blocked = asyncio.Event()
    release = asyncio.Event()

    async def slow_runner(_ctx: JobContext) -> JobResult:
        blocked.set()
        await release.wait()
        return JobResult(status=JobStatus.SUCCESS)

    service = SchedulerService(
        session_factory=sm,
        runners={"Inflight": slow_runner},
        auto_pause=AutoPause(snapshot_provider=provider),
    )
    try:
        run_id = await service.trigger(
            "Inflight",
            triggered_by=TriggerKind.SCHEDULED,
        )
        assert run_id > 0
        await blocked.wait()

        # Health degrades while runner is in-flight.
        snapshot_state["value"] = HealthStatus.ERROR

        # New scheduled trigger is suppressed.
        new_run = await service.trigger(
            "Inflight",
            triggered_by=TriggerKind.SCHEDULED,
        )
        assert new_run == -1

        # The original in-flight run completes normally.
        release.set()
        await service.await_run(run_id)
    finally:
        release.set()
        await service.stop()

    async with sm() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "success"


# ---------------------------------------------------------------------------
# Sanity — PAUSING_STATUSES tracked exactly the spec calls out
# ---------------------------------------------------------------------------


def test_pausing_statuses_only_error() -> None:
    """If a future change adds ``warning`` to the pause set,
    this test catches it — the spec is explicit that warnings
    are informational only."""
    assert frozenset({"error"}) == PAUSING_STATUSES
