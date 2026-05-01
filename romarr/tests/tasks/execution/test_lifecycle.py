"""JobRun lifecycle helper tests (T031, T032, FR-013)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from romarr.domain import Base
from romarr.tasks.execution.lifecycle import (
    cancel_run,
    fail_run,
    finish_run,
    start_run,
)
from romarr.tasks.models import Job, JobRun
from romarr.tasks.types import JobStatus, TriggerKind


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test in-memory SQLite with one shared connection."""
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


async def _seed_job(
    sm: async_sessionmaker, *, job_id: str = "TestJob"
) -> None:
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
# T031 — start_run creates the row with status='running'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_creates_running_row(
    sm: async_sessionmaker,
) -> None:
    await _seed_job(sm, job_id="StartTest")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="StartTest",
            triggered_by=TriggerKind.MANUAL,
        )
        await session.commit()

    async with sm() as session:
        fetched = await session.get(JobRun, run.id)
        assert fetched is not None
        assert fetched.status == "running"
        assert fetched.triggered_by == "manual"
        assert fetched.finished_at is None
        assert fetched.duration_ms is None


@pytest.mark.asyncio
async def test_start_run_records_triggered_by_user(
    sm: async_sessionmaker,
) -> None:
    """The user FK is optional; populated for manual / command
    triggers carrying an authenticated user from spec 010."""
    from romarr.auth.models import User

    await _seed_job(sm, job_id="UserAttr")
    async with sm() as session:
        session.add(
            User(
                username="alice",
                role="admin",
                is_active=True,
                hashed_password="x",
            )
        )
        await session.commit()
        user_row = await session.execute(
            User.__table__.select().where(User.username == "alice")
        )
        user_id = user_row.first()[0]

    async with sm() as session:
        run = await start_run(
            session,
            job_id="UserAttr",
            triggered_by=TriggerKind.COMMAND,
            triggered_by_user_id=user_id,
        )
        await session.commit()
        assert run.triggered_by_user_id == user_id


# ---------------------------------------------------------------------------
# T032 — finish_run transitions to terminal + mirrors onto Job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finish_run_marks_terminal(
    sm: async_sessionmaker,
) -> None:
    await _seed_job(sm, job_id="FinishTest")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="FinishTest",
            triggered_by=TriggerKind.SCHEDULED,
        )
        await session.commit()
        run_id = run.id

    # Small delay so duration_ms is non-zero.
    await asyncio.sleep(0.02)

    async with sm() as session:
        await finish_run(
            session,
            job_run_id=run_id,
            status=JobStatus.SUCCESS,
            items_processed=42,
            output_summary={"processed": 42},
        )
        await session.commit()

    async with sm() as session:
        fetched = await session.get(JobRun, run_id)
        assert fetched is not None
        assert fetched.status == "success"
        assert fetched.items_processed == 42
        assert fetched.output_summary == {"processed": 42}
        assert fetched.finished_at is not None
        assert fetched.duration_ms is not None
        assert fetched.duration_ms > 0


@pytest.mark.asyncio
async def test_finish_run_mirrors_onto_job(
    sm: async_sessionmaker,
) -> None:
    """The parent Job row's ``last_run_*`` columns are kept in
    sync so the operator UI doesn't need to JOIN."""
    await _seed_job(sm, job_id="MirrorTest")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="MirrorTest",
            triggered_by=TriggerKind.SCHEDULED,
        )
        await session.commit()
        run_id = run.id

    async with sm() as session:
        await finish_run(
            session,
            job_run_id=run_id,
            status=JobStatus.PARTIAL,
            error_message="3 items failed",
        )
        await session.commit()

    async with sm() as session:
        job = await session.get(Job, "MirrorTest")
        assert job is not None
        assert job.last_run_status == "partial"
        assert job.last_run_at is not None
        assert job.last_run_duration_ms is not None
        assert job.last_error == "3 items failed"


@pytest.mark.asyncio
async def test_finish_run_on_missing_row_returns_none(
    sm: async_sessionmaker,
) -> None:
    """Defensive: if the row vanished mid-run, finish_run
    returns None rather than crashing — the scheduler logs a
    warning and moves on."""
    async with sm() as session:
        result = await finish_run(
            session,
            job_run_id=999999,
            status=JobStatus.SUCCESS,
        )
        assert result is None


# ---------------------------------------------------------------------------
# fail_run / cancel_run convenience wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_run_records_error_message(
    sm: async_sessionmaker,
) -> None:
    await _seed_job(sm, job_id="FailTest")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="FailTest",
            triggered_by=TriggerKind.MANUAL,
        )
        await session.commit()
        run_id = run.id

    async with sm() as session:
        await fail_run(
            session,
            job_run_id=run_id,
            error_message="RuntimeError: kaboom",
        )
        await session.commit()

    async with sm() as session:
        fetched = await session.get(JobRun, run_id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == "RuntimeError: kaboom"


@pytest.mark.asyncio
async def test_cancel_run_unforced(sm: async_sessionmaker) -> None:
    await _seed_job(sm, job_id="CancelTest")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="CancelTest",
            triggered_by=TriggerKind.MANUAL,
        )
        await session.commit()
        run_id = run.id

    async with sm() as session:
        await cancel_run(session, job_run_id=run_id)
        await session.commit()

    async with sm() as session:
        fetched = await session.get(JobRun, run_id)
        assert fetched is not None
        assert fetched.status == "cancelled"
        assert fetched.cancellation_forced is False


@pytest.mark.asyncio
async def test_cancel_run_forced_records_flag(
    sm: async_sessionmaker,
) -> None:
    """FR-021 force-terminate path: the
    ``cancellation_forced`` audit column carries the escalation
    so the operator can distinguish "operator cancelled
    cooperatively" from "shutdown handler killed it"."""
    await _seed_job(sm, job_id="ForceCancel")
    async with sm() as session:
        run = await start_run(
            session,
            job_id="ForceCancel",
            triggered_by=TriggerKind.MANUAL,
        )
        await session.commit()
        run_id = run.id

    async with sm() as session:
        await cancel_run(session, job_run_id=run_id, forced=True)
        await session.commit()

    async with sm() as session:
        fetched = await session.get(JobRun, run_id)
        assert fetched is not None
        assert fetched.status == "cancelled"
        assert fetched.cancellation_forced is True
