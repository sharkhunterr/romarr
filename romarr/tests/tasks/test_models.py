"""Job + JobRun model round-trip tests (T006-T008)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.tasks.models import Job, JobRun
from romarr.tasks.schemas import JobUpdate

# ---------------------------------------------------------------------------
# T006 — Job round-trip + CHECK constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_round_trip(async_session: AsyncSession) -> None:
    job = Job(
        id="MissingSearch",
        name="Missing Search",
        type="missing_search",
        schedule_interval_seconds=3600,
        enabled=True,
        is_factory_default=True,
    )
    async_session.add(job)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(Job).where(Job.id == "MissingSearch")
        )
    ).scalar_one()
    assert fetched.name == "Missing Search"
    assert fetched.type == "missing_search"
    assert fetched.schedule_interval_seconds == 3600
    assert fetched.max_concurrent_instances == 1
    assert fetched.max_retries == 3
    assert fetched.is_factory_default is True


@pytest.mark.asyncio
async def test_invalid_type_rejected_by_check(
    async_session: AsyncSession,
) -> None:
    job = Job(
        id="WeirdJob",
        name="Weird",
        type="not-a-real-type",
        schedule_interval_seconds=60,
    )
    async_session.add(job)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_invalid_last_run_status_rejected(
    async_session: AsyncSession,
) -> None:
    job = Job(
        id="BadStatus",
        name="Bad",
        type="custom",
        schedule_interval_seconds=60,
        last_run_status="weird",  # not in the CHECK
    )
    async_session.add(job)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T007 — Pydantic schedule validators (mutually-exclusive + interval floor)
# ---------------------------------------------------------------------------


def test_update_rejects_both_schedule_fields() -> None:
    """Mutually-exclusive cron / interval at the schema layer."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        JobUpdate(
            schedule_cron="0 * * * *",
            schedule_interval_seconds=900,
        )


def test_update_rejects_interval_under_30_seconds() -> None:
    """The 30 s floor blocks accidental tight loops at save time."""
    with pytest.raises(ValueError, match="greater than or equal to 30"):
        JobUpdate(schedule_interval_seconds=10)


def test_update_accepts_only_cron() -> None:
    schema = JobUpdate(schedule_cron="0 */15 * * *")
    assert schema.schedule_cron == "0 */15 * * *"
    assert schema.schedule_interval_seconds is None


def test_update_accepts_only_interval() -> None:
    schema = JobUpdate(schedule_interval_seconds=900)
    assert schema.schedule_interval_seconds == 900
    assert schema.schedule_cron is None


def test_update_accepts_neither_schedule_field() -> None:
    """An update touching only ``enabled`` shouldn't be rejected
    just because it didn't supply a schedule field."""
    schema = JobUpdate(enabled=False)
    assert schema.enabled is False
    assert schema.schedule_cron is None
    assert schema.schedule_interval_seconds is None


# ---------------------------------------------------------------------------
# T008 — JobRun round-trip + CASCADE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_run_round_trip(async_session: AsyncSession) -> None:
    job = Job(
        id="HealthCheck",
        name="Health Check",
        type="health_check",
        schedule_interval_seconds=120,
    )
    async_session.add(job)
    await async_session.commit()

    started = datetime.now(UTC)
    run = JobRun(
        job_id="HealthCheck",
        started_at=started,
        status="running",
        triggered_by="scheduled",
    )
    async_session.add(run)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(JobRun).where(JobRun.job_id == "HealthCheck")
        )
    ).scalar_one()
    assert fetched.status == "running"
    assert fetched.triggered_by == "scheduled"
    assert fetched.cancellation_forced is False
    assert fetched.items_processed == 0


@pytest.mark.asyncio
async def test_job_run_invalid_status_rejected(
    async_session: AsyncSession,
) -> None:
    job = Job(
        id="X",
        name="x",
        type="custom",
        schedule_interval_seconds=60,
    )
    async_session.add(job)
    await async_session.commit()

    run = JobRun(
        job_id="X",
        started_at=datetime.now(UTC),
        status="weird",
        triggered_by="manual",
    )
    async_session.add(run)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_job_run_invalid_trigger_rejected(
    async_session: AsyncSession,
) -> None:
    job = Job(
        id="Y",
        name="y",
        type="custom",
        schedule_interval_seconds=60,
    )
    async_session.add(job)
    await async_session.commit()

    run = JobRun(
        job_id="Y",
        started_at=datetime.now(UTC),
        status="running",
        triggered_by="api",  # not in the CHECK
    )
    async_session.add(run)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_job_run_cascade_on_job_delete(
    async_session: AsyncSession,
) -> None:
    """Deleting a job removes its history rows."""
    job = Job(
        id="Cascading",
        name="cascading",
        type="custom",
        schedule_interval_seconds=60,
    )
    async_session.add(job)
    await async_session.commit()

    run = JobRun(
        job_id="Cascading",
        started_at=datetime.now(UTC),
        status="success",
        triggered_by="manual",
    )
    async_session.add(run)
    await async_session.commit()
    run_id = run.id

    await async_session.delete(job)
    await async_session.commit()

    assert (
        await async_session.execute(
            select(JobRun).where(JobRun.id == run_id)
        )
    ).scalar_one_or_none() is None
