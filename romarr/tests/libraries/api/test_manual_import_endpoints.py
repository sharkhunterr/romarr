"""Manual-import endpoint tests (spec 009 T079)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_USER, User, hash_password


async def _seed_user(api_engine: AsyncEngine, *, role: str) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username=f"{role}-user",
                role=role,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()


async def _login(client: httpx.AsyncClient, role: str) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": f"{role}-user", "password": "goodpassword"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_listing_returns_candidates(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """GET /api/v3/rom/manual-import?folder=... returns the
    candidate grid without writing to DB."""
    await _seed_user(api_engine, role=ROLE_ADMIN)
    folder = tmp_path / "import"
    folder.mkdir()
    for i in range(3):
        (folder / f"rom-{i}.md").write_bytes(b"\x00" * 256)

    api_client._transport.app.state.db_sessionmaker = async_sessionmaker(  # type: ignore[attr-defined]
        api_engine, expire_on_commit=False
    )

    await _login(api_client, ROLE_ADMIN)
    response = await api_client.get(
        "/api/v3/rom/manual-import",
        params={"folder": str(folder)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 3
    assert all("path" in entry for entry in body)
    assert all(entry["size_bytes"] == 256 for entry in body)


@pytest.mark.asyncio
async def test_get_listing_rejects_relative_folder(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """The folder= parameter must be absolute — guards the
    path-traversal surface (CL007)."""
    await _seed_user(api_engine, role=ROLE_ADMIN)

    api_client._transport.app.state.db_sessionmaker = async_sessionmaker(  # type: ignore[attr-defined]
        api_engine, expire_on_commit=False
    )

    await _login(api_client, ROLE_ADMIN)
    response = await api_client.get(
        "/api/v3/rom/manual-import",
        params={"folder": "relative/path"},
    )
    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        assert detail["errorCode"] == "invalid_folder"
    else:
        assert body.get("errorCode") == "invalid_folder"


@pytest.mark.asyncio
async def test_post_bulk_runs_each_entry(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """POST /api/v3/rom/manual-import bulk imports each entry
    via the orchestrator + returns one result per entry."""
    await _seed_user(api_engine, role=ROLE_ADMIN)
    folder = tmp_path / "post"
    folder.mkdir()
    paths = []
    for i in range(2):
        path = folder / f"rom-{i}.md"
        path.write_bytes(b"\x00" * 256)
        paths.append(path)

    api_client._transport.app.state.db_sessionmaker = async_sessionmaker(  # type: ignore[attr-defined]
        api_engine, expire_on_commit=False
    )

    await _login(api_client, ROLE_ADMIN)
    response = await api_client.post(
        "/api/v3/rom/manual-import",
        json={
            "entries": [
                {"path": str(paths[0]), "action": "import"},
                {"path": str(paths[1]), "action": "skip"},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    assert body[0]["action"] == "import"
    assert body[0]["history_id"] is not None
    assert body[1]["action"] == "skip"
    assert body[1]["history_id"] is None


@pytest.mark.asyncio
async def test_listing_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Both endpoints are admin-gated."""
    response = await api_client.get(
        "/api/v3/rom/manual-import",
        params={"folder": str(tmp_path)},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_listing_user_role_returns_403(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """User-role principals are blocked — admin only (CL007)."""
    await _seed_user(api_engine, role=ROLE_USER)

    api_client._transport.app.state.db_sessionmaker = async_sessionmaker(  # type: ignore[attr-defined]
        api_engine, expire_on_commit=False
    )

    await _login(api_client, ROLE_USER)
    response = await api_client.get(
        "/api/v3/rom/manual-import",
        params={"folder": str(tmp_path)},
    )
    assert response.status_code == 403
