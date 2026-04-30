"""Download-client CRUD endpoint tests (T057-T061)."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.downloaders.models import DownloadClient
from tests.downloaders.api.conftest import seed_admin_and_login

_QBIT_PAYLOAD: dict[str, object] = {
    "name": "Local qBit",
    "type": "qbittorrent",
    "host": "qbit.test",
    "port": 8080,
    "username": "admin",
    "password": "adminpass",
    "enable_for_torrents": True,
}

_SAB_PAYLOAD: dict[str, object] = {
    "name": "SAB",
    "type": "sabnzbd",
    "host": "sab.test",
    "port": 8080,
    "api_key": "sab-key",
    "enable_for_usenet": True,
}


# ---------------------------------------------------------------------------
# Auth gating (CL005 / FR-026a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v3/downloadclient")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Create + persist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_qbit(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post("/api/v3/downloadclient", json=_QBIT_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Local qBit"
    assert body["type"] == "qbittorrent"
    assert body["is_configured"] is True
    # Encrypted blob must NEVER leak in any response.
    assert "password" not in body
    assert "password_encrypted" not in body
    assert "api_key" not in body


@pytest.mark.asyncio
async def test_create_persists_sab(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post("/api/v3/downloadclient", json=_SAB_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "sabnzbd"
    assert body["is_configured"] is True


# ---------------------------------------------------------------------------
# T057 — POST ?test=true probes connectivity first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_with_test_true_persists_on_happy_path(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)

    with respx.mock:
        respx.get("http://sab.test:8080/api").mock(
            side_effect=lambda req: httpx.Response(
                200,
                json=(
                    {"version": "4.3.2"}
                    if req.url.params.get("mode") == "version"
                    else {"categories": ["romarr", "default"]}
                ),
            )
        )
        response = await api_client.post(
            "/api/v3/downloadclient?test=true", json=_SAB_PAYLOAD
        )

    assert response.status_code == 201

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (await session.execute(select(DownloadClient))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_post_with_test_true_rejects_on_auth_failure(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T057 fail path: connectivity probe rejects → HTTP 400, zero rows persisted."""
    await seed_admin_and_login(api_engine, api_client)

    with respx.mock:
        respx.get("http://sab.test:8080/api").mock(
            return_value=httpx.Response(
                200,
                json={"status": False, "error": "API Key Incorrect"},
            )
        )
        response = await api_client.post(
            "/api/v3/downloadclient?test=true", json=_SAB_PAYLOAD
        )

    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth"

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (await session.execute(select(DownloadClient))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# T058 — PUT re-encrypts only when the secret is present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_re_encrypts_when_password_present(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/downloadclient", json=_QBIT_PAYLOAD)
    client_id = create.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        original = (
            await session.execute(
                select(DownloadClient).where(DownloadClient.id == client_id)
            )
        ).scalar_one()
        original_blob = original.password_encrypted

    # PUT WITHOUT password — ciphertext untouched.
    put_no_pw = await api_client.put(
        f"/api/v3/downloadclient/{client_id}", json={"name": "Renamed"}
    )
    assert put_no_pw.status_code == 200
    async with sm() as session:
        row = (
            await session.execute(
                select(DownloadClient).where(DownloadClient.id == client_id)
            )
        ).scalar_one()
        assert row.password_encrypted == original_blob
        assert row.name == "Renamed"

    # PUT WITH password — ciphertext rotated.
    put_with_pw = await api_client.put(
        f"/api/v3/downloadclient/{client_id}", json={"password": "newpass"}
    )
    assert put_with_pw.status_code == 200
    async with sm() as session:
        row = (
            await session.execute(
                select(DownloadClient).where(DownloadClient.id == client_id)
            )
        ).scalar_one()
        assert row.password_encrypted != original_blob


# ---------------------------------------------------------------------------
# T059 — POST duplicate (type, host, port) → HTTP 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_duplicate_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    first = await api_client.post("/api/v3/downloadclient", json=_QBIT_PAYLOAD)
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v3/downloadclient",
        json={**_QBIT_PAYLOAD, "name": "Different name"},
    )
    assert second.status_code == 409
    assert second.json()["errorCode"] == "duplicate"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/downloadclient", json=_QBIT_PAYLOAD)
    client_id = create.json()["id"]

    delete = await api_client.delete(f"/api/v3/downloadclient/{client_id}")
    assert delete.status_code == 204

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(DownloadClient).where(DownloadClient.id == client_id)
            )
        ).scalar_one_or_none()
    assert row is None


# ---------------------------------------------------------------------------
# T060 — POST /{id}/test runs connectivity probe against the persisted row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_endpoint_runs_connectivity(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/downloadclient", json=_SAB_PAYLOAD)
    client_id = create.json()["id"]

    with respx.mock:
        respx.get("http://sab.test:8080/api").mock(
            side_effect=lambda req: httpx.Response(
                200,
                json=(
                    {"version": "4.3.2"}
                    if req.url.params.get("mode") == "version"
                    else {"categories": ["romarr", "default"]}
                ),
            )
        )
        response = await api_client.post(
            f"/api/v3/downloadclient/{client_id}/test"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["client_version"] == "SABnzbd v4.3.2"
    assert body["warnings"] == []


@pytest.mark.asyncio
async def test_test_endpoint_surfaces_warnings(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """SAB without 'romarr' category → ok=True with category_missing warning."""
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/downloadclient", json=_SAB_PAYLOAD)
    client_id = create.json()["id"]

    with respx.mock:
        respx.get("http://sab.test:8080/api").mock(
            side_effect=lambda req: httpx.Response(
                200,
                json=(
                    {"version": "4.3.2"}
                    if req.url.params.get("mode") == "version"
                    else {"categories": ["default"]}  # no 'romarr'
                ),
            )
        )
        response = await api_client.post(
            f"/api/v3/downloadclient/{client_id}/test"
        )

    body = response.json()
    assert body["ok"] is True
    assert body["warnings"][0]["code"] == "category_missing"


# ---------------------------------------------------------------------------
# List + read round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_and_get_round_trip(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/downloadclient", json=_QBIT_PAYLOAD)
    client_id = create.json()["id"]

    listing = await api_client.get("/api/v3/downloadclient")
    assert listing.status_code == 200
    assert any(r["id"] == client_id for r in listing.json())

    one = await api_client.get(f"/api/v3/downloadclient/{client_id}")
    assert one.status_code == 200
    assert one.json()["id"] == client_id
