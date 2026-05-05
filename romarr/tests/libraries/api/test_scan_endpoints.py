"""Library scan-trigger endpoint tests (spec 009 T076)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.libraries.models import Library
from romarr.tasks.models import Job
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.types import JobContext, JobResult, JobStatus

from tests.libraries.api.conftest import seed_profiles


async def _seed_admin(api_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="scan-admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()


async def _seed_scan_job(api_engine: AsyncEngine) -> None:
    """LibraryScan must exist as an enabled job row for the
    scheduler to accept the trigger."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Job(
                id="LibraryScan",
                name="library-scan",
                type="library_scan",
                schedule_cron="0 4 * * *",
                enabled=True,
            )
        )
        await session.commit()


async def _seed_library(api_engine: AsyncEngine) -> int:
    profile_ids = await seed_profiles(api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        library = Library(
            name="Cartridges",
            path="/srv/roms/cartridges",
            quality_profile_id=profile_ids["quality_profile_id"],
            region_profile_id=profile_ids["region_profile_id"],
            dump_profile_id=profile_ids["dump_profile_id"],
            language_profile_id=profile_ids["language_profile_id"],
            naming_profile_id=profile_ids["naming_profile_id"],
        )
        session.add(library)
        await session.commit()
        await session.refresh(library)
        return library.id


def _wire_scheduler(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    runner_calls: list[JobContext],
) -> SchedulerService:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)

    async def runner(ctx: JobContext) -> JobResult:
        runner_calls.append(ctx)
        return JobResult(status=JobStatus.SUCCESS)

    scheduler = SchedulerService(
        session_factory=sm,
        runners={"LibraryScan": runner},
    )
    api_client._transport.app.state.scheduler = scheduler  # type: ignore[attr-defined]
    api_client._transport.app.state.db_sessionmaker = sm  # type: ignore[attr-defined]
    return scheduler


async def _login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": "scan-admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_scan_all_returns_command_id(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """POST /api/v3/rom/scan triggers LibraryScan; the response
    carries the new JobRun id + Sonarr-shape envelope."""
    await _seed_admin(api_engine)
    await _seed_scan_job(api_engine)

    runner_calls: list[JobContext] = []
    scheduler = _wire_scheduler(api_client, api_engine, runner_calls)
    try:
        await _login(api_client)
        response = await api_client.post("/api/v3/rom/scan")
        assert response.status_code == 201, response.text
        body = response.json()
        assert isinstance(body["id"], int)
        assert body["name"] == "LibraryScan"
        assert body["trigger"] == "manual"
        await scheduler.await_run(body["id"])
        assert len(runner_calls) == 1
        # No libraryId in parameters when scanning everything.
        assert runner_calls[0].parameters == {}
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scan_one_library_forwards_libraryId_parameter(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """POST /api/v3/rom/library/{id}/scan forwards libraryId to
    the runner so :class:`LibraryScanAdapter` scopes the scan."""
    await _seed_admin(api_engine)
    await _seed_scan_job(api_engine)
    library_id = await _seed_library(api_engine)

    runner_calls: list[JobContext] = []
    scheduler = _wire_scheduler(api_client, api_engine, runner_calls)
    try:
        await _login(api_client)
        response = await api_client.post(
            f"/api/v3/rom/library/{library_id}/scan"
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert isinstance(body["id"], int)
        await scheduler.await_run(body["id"])
        assert len(runner_calls) == 1
        assert runner_calls[0].parameters == {"libraryId": library_id}
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scan_unknown_library_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The path-scoped variant validates the library exists
    before triggering — operators get a clean 404 instead of a
    spurious JobRun for a deleted library."""
    await _seed_admin(api_engine)
    await _seed_scan_job(api_engine)

    runner_calls: list[JobContext] = []
    scheduler = _wire_scheduler(api_client, api_engine, runner_calls)
    try:
        await _login(api_client)
        response = await api_client.post("/api/v3/rom/library/9999/scan")
        assert response.status_code == 404
        body = response.json()
        # Spec 013 envelope keeps errorCode under detail.
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail["errorCode"] == "library_not_found"
        else:
            assert body.get("errorCode") == "library_not_found"
        # No runner fired — the validation check killed it before
        # the scheduler.trigger call.
        assert runner_calls == []
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scan_unauthenticated_returns_401(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Both scan endpoints are admin-gated."""
    response = await api_client.post("/api/v3/rom/scan")
    assert response.status_code == 401
