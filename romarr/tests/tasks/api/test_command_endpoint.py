"""Sonarr-compat command endpoint tests (T060, T061)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_READONLY, User, hash_password
from romarr.tasks.models import Job
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


async def _seed_jobs(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Job(
                id="MissingSearch",
                name="missing",
                type="missing_search",
                schedule_cron="0 */12 * * *",
            )
        )
        session.add(
            Job(
                id="RefreshGameMetadata",
                name="refresh-meta",
                type="refresh_metadata",
                schedule_cron="0 3 * * *",
            )
        )
        await session.commit()


async def _login(client: httpx.AsyncClient, username: str) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": username, "password": "goodpassword"},
    )
    assert response.status_code == 204


def _wire_scheduler(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    runners: dict[str, Any],
) -> SchedulerService:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    scheduler = SchedulerService(
        session_factory=sm,
        runners=runners,
    )
    api_client._transport.app.state.scheduler = scheduler  # type: ignore[attr-defined]
    api_client._transport.app.state.db_sessionmaker = sm  # type: ignore[attr-defined]
    return scheduler


# ---------------------------------------------------------------------------
# T060 — POST /api/v3/command returns Sonarr-shaped status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_known_command_returns_201_with_status(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)

    runner_calls: list[JobContext] = []

    async def runner(ctx: JobContext) -> JobResult:
        runner_calls.append(ctx)
        return JobResult(status=JobStatus.SUCCESS)

    scheduler = _wire_scheduler(
        api_client, api_engine, runners={"MissingSearch": runner}
    )
    try:
        await _login(api_client, "admin")
        response = await api_client.post(
            "/api/v3/command", json={"name": "MissingSearch"}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        # Sonarr-shape fields present.
        assert "id" in body
        assert body["name"] == "MissingSearch"
        assert body["commandName"] == "MissingSearch"
        assert body["status"] in ("started", "completed")
        assert "started" in body
        assert body["triggeredBy"] == "command"

        await scheduler.await_run(body["id"])
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_get_command_status_returns_running_in_flight(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The Sonarr-shape ``status`` field reflects the runner
    state. While the runner is in-flight, GET on the command
    id returns ``"started"``. The completion path is
    integration-tested at the scheduler unit level (slice 11)
    — repeating it here would race the SQLAlchemy connection
    cache without adding coverage."""
    import asyncio as _asyncio

    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)

    pending = _asyncio.Event()
    release = _asyncio.Event()

    async def runner(_ctx: JobContext) -> JobResult:
        pending.set()
        await release.wait()
        return JobResult(status=JobStatus.SUCCESS)

    scheduler = _wire_scheduler(
        api_client, api_engine, runners={"MissingSearch": runner}
    )
    try:
        await _login(api_client, "admin")
        post_resp = await api_client.post(
            "/api/v3/command", json={"name": "MissingSearch"}
        )
        assert post_resp.status_code == 201
        run_id = post_resp.json()["id"]
        await pending.wait()  # runner is now in-flight

        get_resp = await api_client.get(f"/api/v3/command/{run_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["id"] == run_id
        assert body["name"] == "MissingSearch"
        assert body["commandName"] == "MissingSearch"
        assert body["status"] == "started"
        assert body["ended"] is None
    finally:
        release.set()
        await scheduler.stop()


# ---------------------------------------------------------------------------
# T061 — kwargs pass through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kwargs_flow_into_job_context(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)

    runner_calls: list[JobContext] = []

    async def runner(ctx: JobContext) -> JobResult:
        runner_calls.append(ctx)
        return JobResult(status=JobStatus.SUCCESS)

    scheduler = _wire_scheduler(
        api_client,
        api_engine,
        runners={"RefreshGameMetadata": runner},
    )
    try:
        await _login(api_client, "admin")
        response = await api_client.post(
            "/api/v3/command",
            json={"name": "RefreshGame", "gameId": 42},
        )
        assert response.status_code == 201, response.text
        run_id = response.json()["id"]
        await scheduler.await_run(run_id)

        assert len(runner_calls) == 1
        # ``gameId`` flows through as the camelCase key — Sonarr
        # consumers use that exact key, so we forward verbatim.
        assert runner_calls[0].parameters == {"gameId": 42}
    finally:
        await scheduler.stop()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_command_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/command", json={"name": "DefinitelyNotASonarrCommand"}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errorCode"] == "unknown_command"


@pytest.mark.asyncio
async def test_missing_name_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.post("/api/v3/command", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["errorCode"] == "invalid_command"


@pytest.mark.asyncio
async def test_post_returns_503_without_scheduler(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/command", json={"name": "MissingSearch"}
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_unknown_command_id_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/command/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.post(
        "/api/v3/command", json={"name": "MissingSearch"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_accessible_to_readonly(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    # 404 because no command exists — but 200/404 both prove
    # auth passed.
    response = await api_client.get("/api/v3/command/1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_known_endpoint_lists_command_names(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/command/_known")
    assert response.status_code == 200
    names = response.json()
    assert "MissingSearch" in names
    assert "RefreshGame" in names


# ---------------------------------------------------------------------------
# T088 — DELETE /api/v3/command/{id} cancels the in-flight command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_unknown_command_id_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.delete("/api/v3/command/999999")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "not_found"


@pytest.mark.asyncio
async def test_delete_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.delete("/api/v3/command/1")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_terminal_command_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A command in a terminal status can't be cancelled — 409
    so the operator UI knows the run completed before the cancel
    landed."""
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from romarr.tasks.models import JobRun

    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        run = JobRun(
            job_id="MissingSearch",
            started_at=_datetime.now(_UTC),
            finished_at=_datetime.now(_UTC),
            status="success",
            triggered_by="manual",
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        await session.commit()

    await _login(api_client, "admin")
    response = await api_client.delete(f"/api/v3/command/{run_id}")
    assert response.status_code == 409
    assert response.json()["errorCode"] == "command_terminal"


@pytest.mark.asyncio
async def test_delete_returns_503_without_registry(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No CancellationRegistry on app.state ⇒ 503."""
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from romarr.tasks.models import JobRun

    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        run = JobRun(
            job_id="MissingSearch",
            started_at=_datetime.now(_UTC),
            status="running",
            triggered_by="manual",
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        await session.commit()

    await _login(api_client, "admin")
    response = await api_client.delete(f"/api/v3/command/{run_id}")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "cancellation_unavailable"


@pytest.mark.asyncio
async def test_delete_cancels_in_flight_command(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T088: when the registry is wired, DELETE on the command
    id signals cancellation; the run transitions to ``cancelled``
    and the response carries ``forced: false`` (cooperative)."""
    import asyncio as _asyncio

    from romarr.tasks.execution.cancellation import CancellationRegistry

    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_jobs(api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)

    registry = CancellationRegistry(force_terminate_after_seconds=2.0)

    async def cooperative(ctx: JobContext) -> JobResult:
        await ctx.cancellation_event.wait()
        return JobResult(status=JobStatus.CANCELLED)

    scheduler = SchedulerService(
        session_factory=sm,
        runners={"MissingSearch": cooperative},
        cancellation_registry=registry,
    )

    api_client._transport.app.state.scheduler = scheduler  # type: ignore[attr-defined]
    api_client._transport.app.state.cancellation_registry = registry  # type: ignore[attr-defined]
    api_client._transport.app.state.db_sessionmaker = sm  # type: ignore[attr-defined]

    try:
        await _login(api_client, "admin")
        run_id = await scheduler.trigger("MissingSearch")
        # Yield so the runner registers + reaches its await.
        for _ in range(5):
            await _asyncio.sleep(0)

        response = await api_client.delete(f"/api/v3/command/{run_id}")
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["id"] == run_id
        assert body["status"] == "cancelled"
        assert body["forced"] is False
    finally:
        await scheduler.stop()
