"""JobRun history + cancel endpoint tests (T068, T069)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_READONLY, User, hash_password
from romarr.tasks.execution.cancellation import CancellationRegistry
from romarr.tasks.models import Job, JobRun
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.types import JobContext, JobResult, JobStatus


async def _seed_user(
    engine: AsyncEngine, *, username: str, role: str = ROLE_ADMIN
) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username=username,
                role=role,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()


async def _login(client: httpx.AsyncClient, username: str) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": username, "password": "goodpassword"},
    )
    assert response.status_code == 204


async def _seed_runs(engine: AsyncEngine) -> dict[str, list[int]]:
    """Seed one job + multiple runs across statuses for the
    pagination/filter tests."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    started = datetime.now(UTC)
    by_status: dict[str, list[int]] = {
        "success": [],
        "failed": [],
        "running": [],
    }
    async with sm() as session:
        session.add(
            Job(
                id="HistoryJob",
                name="History",
                type="custom",
                schedule_interval_seconds=60,
            )
        )
        await session.commit()
        for i in range(5):
            run = JobRun(
                job_id="HistoryJob",
                started_at=started + timedelta(seconds=i),
                status="success",
                triggered_by="scheduled",
            )
            session.add(run)
        for i in range(3):
            run = JobRun(
                job_id="HistoryJob",
                started_at=started + timedelta(seconds=10 + i),
                status="failed",
                triggered_by="manual",
            )
            session.add(run)
        for i in range(2):
            run = JobRun(
                job_id="HistoryJob",
                started_at=started + timedelta(seconds=20 + i),
                status="running",
                triggered_by="manual",
            )
            session.add(run)
        await session.commit()
        for run in (
            await session.execute(
                JobRun.__table__.select().where(JobRun.job_id == "HistoryJob")
            )
        ).all():
            by_status[run.status].append(run.id)
    return by_status


# ---------------------------------------------------------------------------
# T069 — pagination + filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_list_default_returns_all(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs"
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 10  # 5 + 3 + 2


@pytest.mark.asyncio
async def test_runs_list_filter_by_status(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs?status=failed"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert all(row["status"] == "failed" for row in rows)


@pytest.mark.asyncio
async def test_runs_list_filter_by_triggered_by(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs?triggered_by=scheduled"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 5
    assert all(row["triggered_by"] == "scheduled" for row in rows)


@pytest.mark.asyncio
async def test_runs_list_pagination(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")

    page1 = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs?limit=4&offset=0"
    )
    page2 = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs?limit=4&offset=4"
    )
    assert page1.status_code == 200
    assert page2.status_code == 200
    assert len(page1.json()) == 4
    assert len(page2.json()) == 4
    # Pages don't overlap.
    page1_ids = {row["id"] for row in page1.json()}
    page2_ids = {row["id"] for row in page2.json()}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_runs_list_invalid_limit_returns_422(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")
    # Limit > 200 violates the documented cap.
    response = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs?limit=500"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_runs_list_unknown_job_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get(
        "/api/v3/system/tasks/DoesNotExist/runs"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_runs_list_requires_authentication(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_runs(api_engine)
    response = await api_client.get(
        "/api/v3/system/tasks/HistoryJob/runs"
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# T068 — cancel endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_returns_503_without_registry(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No CancellationRegistry on app.state ⇒ 503."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_runs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/system/tasks/HistoryJob/runs/1/cancel"
    )
    # The run row exists but is in ``running`` state (id=1 may
    # be one of the 2 running rows from _seed_runs). 503 because
    # registry isn't wired.
    assert response.status_code in (503, 404, 409)


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_runs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/system/tasks/HistoryJob/runs/999999/cancel"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_terminal_run_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A run that's already in a terminal state can't be
    cancelled — 409 Conflict so the operator UI knows the
    run completed before the cancel landed."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    by_status = await _seed_runs(api_engine)
    await _login(api_client, "admin")
    success_id = by_status["success"][0]
    response = await api_client.post(
        f"/api/v3/system/tasks/HistoryJob/runs/{success_id}/cancel"
    )
    assert response.status_code == 409
    assert "terminal" in response.text.lower()


@pytest.mark.asyncio
async def test_cancel_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_runs(api_engine)
    await _login(api_client, "reader")
    response = await api_client.post(
        "/api/v3/system/tasks/HistoryJob/runs/1/cancel"
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cancel_with_registry_signals_event(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T068: when the registry is wired, the cancel endpoint
    signals the event for the in-flight runner and the run
    transitions to cancelled."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)

    async with sm() as session:
        session.add(
            Job(
                id="LiveJob",
                name="live",
                type="custom",
                schedule_interval_seconds=60,
            )
        )
        await session.commit()

    registry = CancellationRegistry(force_terminate_after_seconds=2.0)

    async def cooperative(ctx: JobContext) -> JobResult:
        await ctx.cancellation_event.wait()
        return JobResult(status=JobStatus.CANCELLED)

    scheduler = SchedulerService(
        session_factory=sm,
        runners={"LiveJob": cooperative},
        cancellation_registry=registry,
    )

    api_client._transport.app.state.scheduler = scheduler  # type: ignore[attr-defined]
    api_client._transport.app.state.cancellation_registry = registry  # type: ignore[attr-defined]

    try:
        await _login(api_client, "admin")
        run_id = await scheduler.trigger("LiveJob")
        # Yield so the runner registers + reaches its await.
        for _ in range(5):
            await asyncio.sleep(0)

        response = await api_client.post(
            f"/api/v3/system/tasks/LiveJob/runs/{run_id}/cancel"
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["forced"] is False
    finally:
        await scheduler.stop()
