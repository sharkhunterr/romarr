"""Preview endpoint + scheduled sync runner + seed check."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.platform_packs.models import PackSource
from romarr.tasks.models import Job
from romarr.tasks.runner_protocol import build_default_registry
from romarr.tasks.seeder import DEFAULT_CATALOGUE, seed_defaults


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    r = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert r.status_code == 204


def _patch_httpx_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> None:
    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *a: object, **kw: object) -> None:  # noqa: ANN401
        kw.pop("transport", None)
        orig_init(self, *a, transport=transport, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


@pytest.mark.asyncio
async def test_preview_reports_would_fail_for_garbage_yaml(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)

    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={"name": "Test", "url": "https://example.com/pack.yaml"},
    )
    sid = r.json()["id"]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not: valid: yaml: pack")

    _patch_httpx_transport(monkeypatch, handler)

    r = await api_client.post(
        f"/api/v3/rom/platform-pack-source/{sid}/preview"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["action"] == "would_fail"
    assert item["error_message"] is not None


@pytest.mark.asyncio
async def test_preview_returns_502_on_fetch_error(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={"name": "T", "url": "https://example.com/pack.yaml"},
    )
    sid = r.json()["id"]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    _patch_httpx_transport(monkeypatch, handler)

    r = await api_client.post(
        f"/api/v3/rom/platform-pack-source/{sid}/preview"
    )
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_scheduler_seed_installs_pack_sources_sync(
    async_engine: AsyncEngine,
) -> None:
    sm = async_sessionmaker(async_engine, expire_on_commit=False)
    async with sm() as session:
        inserted = await seed_defaults(session)
    assert inserted >= 1
    async with sm() as session:
        row = (
            await session.execute(
                select(Job).where(Job.id == "PackSourcesSync")
            )
        ).scalar_one()
    assert row.enabled is False  # off-by-default per spec choice
    assert row.schedule_cron == "0 5 * * *"


def test_pack_sources_sync_in_default_catalogue() -> None:
    ids = {j.job_id for j in DEFAULT_CATALOGUE}
    assert "PackSourcesSync" in ids


def test_pack_sources_sync_wired_in_registry() -> None:
    reg = build_default_registry()
    assert "PackSourcesSync" in reg


@pytest.mark.asyncio
async def test_runner_sweeps_zero_sources_cleanly(
    async_engine: AsyncEngine,
) -> None:
    """With no PackSource rows the runner returns an empty result."""
    from romarr.tasks.runners.pack_sources_sync import run_pack_sources_sync

    sm = async_sessionmaker(async_engine, expire_on_commit=False)
    async with sm() as session:
        result = await run_pack_sources_sync(session, sessionmaker=sm)
    assert result.total_sources == 0
    assert result.total_applied == 0
    assert result.outcomes == []


@pytest.mark.asyncio
async def test_runner_marks_error_on_remote_failure(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from romarr.tasks.runners.pack_sources_sync import run_pack_sources_sync

    sm = async_sessionmaker(async_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            PackSource(
                name="Broken",
                url="https://x.example/bad.yaml",
                kind="raw",
                enabled=True,
            )
        )
        await session.commit()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server exploded")

    _patch_httpx_transport(monkeypatch, handler)

    async with sm() as session:
        result = await run_pack_sources_sync(session, sessionmaker=sm)

    assert result.total_sources == 1
    assert result.total_applied == 0
    assert len(result.outcomes) == 1
    assert result.outcomes[0].status == "error"

    async with sm() as session:
        row = (
            await session.execute(
                select(PackSource).where(PackSource.name == "Broken")
            )
        ).scalar_one()
    assert row.last_status == "error"
    assert row.last_error is not None
