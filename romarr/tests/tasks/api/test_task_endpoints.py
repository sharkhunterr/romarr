"""Tasks API tests (T064-T067, T070, FR-024-FR-026)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_READONLY, User, hash_password
from romarr.tasks.models import Job


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


async def _login(
    client: httpx.AsyncClient, username: str
) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": username, "password": "goodpassword"},
    )
    assert response.status_code == 204


async def _seed_jobs(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Job(
                id="MissingSearch",
                name="Missing Search",
                type="missing_search",
                schedule_cron="0 */12 * * *",
                enabled=True,
                is_factory_default=True,
            )
        )
        session.add(
            Job(
                id="LibraryScan",
                name="Library Scan",
                type="library_scan",
                schedule_interval_seconds=3600,
                enabled=False,
                is_factory_default=True,
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T064 — list returns status fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_jobs_with_status(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_jobs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.get("/api/v3/system/tasks")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}

    # Documented schema fields are surfaced.
    job = by_id["MissingSearch"]
    assert job["schedule_cron"] == "0 */12 * * *"
    assert job["enabled"] is True
    assert job["next_run_at"] is None
    assert job["last_run_at"] is None
    assert job["is_paused_by_health"] is False
    assert job["current_run_id"] is None


@pytest.mark.asyncio
async def test_get_single_task(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_jobs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.get("/api/v3/system/tasks/MissingSearch")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "MissingSearch"
    assert body["type"] == "missing_search"


@pytest.mark.asyncio
async def test_get_unknown_task_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/system/tasks/DoesNotExist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# T065 — PATCH validates schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_with_both_schedule_fields_rejected(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Pydantic's ``JobUpdate`` rejects both-set with HTTP 422
    via the schema validator; the body's ``mutually exclusive``
    message is in the ``detail`` array."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.patch(
        "/api/v3/system/tasks/MissingSearch",
        json={
            "schedule_cron": "0 * * * *",
            "schedule_interval_seconds": 900,
        },
    )
    assert response.status_code == 422
    assert "mutually exclusive" in response.text.lower()


@pytest.mark.asyncio
async def test_patch_with_sub_30_second_interval_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.patch(
        "/api/v3/system/tasks/LibraryScan",
        json={"schedule_interval_seconds": 10},
    )
    assert response.status_code == 422  # pydantic validation


# ---------------------------------------------------------------------------
# T066 — PATCH applies (without scheduler wiring, just persists)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_persists_new_schedule(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.patch(
        "/api/v3/system/tasks/MissingSearch",
        json={
            "schedule_cron": None,
            "schedule_interval_seconds": 7200,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schedule_cron"] is None
    assert body["schedule_interval_seconds"] == 7200


@pytest.mark.asyncio
async def test_patch_can_disable_a_job(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.patch(
        "/api/v3/system/tasks/MissingSearch",
        json={"enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


# ---------------------------------------------------------------------------
# T070 — admin-only mutations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_jobs(api_engine)
    await _login(api_client, "reader")

    response = await api_client.patch(
        "/api/v3/system/tasks/MissingSearch",
        json={"enabled": False},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_unauthenticated_returns_401(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_jobs(api_engine)
    response = await api_client.patch(
        "/api/v3/system/tasks/MissingSearch",
        json={"enabled": False},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_accessible_to_readonly(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_jobs(api_engine)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/system/tasks")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# T067 — trigger endpoint without scheduler wired returns 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_returns_503_without_scheduler(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Without a SchedulerService on app.state, the trigger
    endpoint surfaces 503 rather than crashing — the lifespan
    integration that wires it lands in the SHUTDOWN slice."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/system/tasks/MissingSearch/trigger",
        json={"kwargs": {}},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_trigger_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_jobs(api_engine)
    await _login(api_client, "reader")
    response = await api_client.post(
        "/api/v3/system/tasks/MissingSearch/trigger",
        json={"kwargs": {}},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Trigger with scheduler wired (integration via app.state)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_with_scheduler_returns_run_id(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """When the test wires a SchedulerService onto app.state,
    the trigger endpoint returns 202 + the new job_run_id."""
    from romarr.tasks.scheduler import SchedulerService
    from romarr.tasks.types import JobResult, JobStatus

    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)

    runner_calls: list[Any] = []

    async def runner(_ctx: Any) -> JobResult:
        runner_calls.append(_ctx)
        return JobResult(status=JobStatus.SUCCESS)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    scheduler = SchedulerService(
        session_factory=sm,
        runners={"MissingSearch": runner},
    )
    api_client._transport.app.state.scheduler = scheduler  # type: ignore[attr-defined]

    try:
        await _login(api_client, "admin")
        response = await api_client.post(
            "/api/v3/system/tasks/MissingSearch/trigger",
            json={"kwargs": {"gameId": 42}},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["job_run_id"] > 0
        await scheduler.await_run(body["job_run_id"])
        assert len(runner_calls) == 1
        assert runner_calls[0].parameters == {"gameId": 42}
    finally:
        await scheduler.stop()
