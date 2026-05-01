"""Notification CRUD + test-endpoint API tests (T058-T063, FR-024, FR-024b)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_READONLY, User, hash_password


async def _seed_user(
    engine: AsyncEngine,
    *,
    username: str,
    password: str = "goodpassword",
    role: str = ROLE_ADMIN,
) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username=username,
                role=role,
                is_active=True,
                hashed_password=hash_password(password),
            )
        )
        await session.commit()


async def _login(
    client: httpx.AsyncClient, username: str, password: str = "goodpassword"
) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 204


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Auth secret needed for the encryption layer used during
    notification create/update."""
    from romarr.config.settings import get_settings

    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-for-notifications",
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# T061 — full CRUD round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_crud_round_trip(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="alice", role=ROLE_ADMIN)
    await _login(api_client, "alice")

    create_payload = {
        "name": "discord-prod",
        "apprise_url": "discord://1234567890/abcdefghijklmnop",
        "on_grab": False,
        "on_import": True,
        "on_upgrade": True,
        "on_fail": True,
        "on_health_issue": True,
        "on_dat_update": False,
        "on_game_added": False,
        "tags": ["family-friendly"],
        "enabled": True,
        "include_health_warnings": True,
        "include_health_errors": True,
    }

    # POST
    create_resp = await api_client.post(
        "/api/v3/notification", json=create_payload
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    notification_id = created["id"]
    assert created["name"] == "discord-prod"
    # FR-024 — never expose the plaintext URL.
    assert "apprise_url" not in created
    assert created["apprise_url_redacted"] == "discord://..."

    # GET list
    list_resp = await api_client.get("/api/v3/notification")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == notification_id

    # GET single
    read_resp = await api_client.get(
        f"/api/v3/notification/{notification_id}"
    )
    assert read_resp.status_code == 200
    fetched = read_resp.json()
    assert fetched["apprise_url_redacted"] == "discord://..."
    assert "apprise_url" not in fetched

    # PUT
    update_payload = {"on_grab": True}
    update_resp = await api_client.put(
        f"/api/v3/notification/{notification_id}",
        json=update_payload,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["on_grab"] is True

    # DELETE
    delete_resp = await api_client.delete(
        f"/api/v3/notification/{notification_id}"
    )
    assert delete_resp.status_code == 204

    # Confirm gone.
    confirm_resp = await api_client.get(
        f"/api/v3/notification/{notification_id}"
    )
    assert confirm_resp.status_code == 404


# ---------------------------------------------------------------------------
# T062 — read responses NEVER expose the plaintext URL (FR-024)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_redacted_url(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    create_resp = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "tgram-prod",
            "apprise_url": "tgram://12345:abcde/-100123456",
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["apprise_url_redacted"] == "tgram://..."
    assert "tgram://12345:abcde" not in str(body)


# ---------------------------------------------------------------------------
# T063 — bad Apprise URL ⇒ 400 with structured detail (FR-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_apprise_url_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "broken",
            "apprise_url": "not-a-real-scheme://nonsense",
        },
    )
    assert response.status_code == 400
    assert "apprise" in response.json()["errorMessage"].lower()


# ---------------------------------------------------------------------------
# Bad template at save time ⇒ 400 (FR-013)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_template_rejected_at_save(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    response = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "template-broken",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
            "on_import_format": "{{ unknown_variable }}",
        },
    )
    assert response.status_code == 400
    assert "on_import_format" in response.json()["errorMessage"]


# ---------------------------------------------------------------------------
# FR-024b — mutating endpoints require admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A readonly user can read but cannot POST."""
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "x",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_create_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "x",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_readonly_can_list(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/notification")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Schema endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_lists_implementations(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.get("/api/v3/notification/schema")
    assert response.status_code == 200
    body = response.json()
    implementations = {entry["implementation"] for entry in body}
    assert implementations == {"apprise", "webhook"}


# ---------------------------------------------------------------------------
# T058/T059 — synthetic test endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_endpoint_flows_through_dispatcher(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T058: pressing test fires a synthetic OnImport with
    placeholder data through the same dispatcher real events
    use. We patch ``apprise.notify`` so no real network call
    happens."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    create_resp = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "test-target",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
        },
    )
    notification_id = create_resp.json()["id"]

    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )

    response = await api_client.post(
        f"/api/v3/notification/{notification_id}/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_test_endpoint_returns_structured_error(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T059: an unreachable target surfaces success=false with
    a structured error message."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    create_resp = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "test-fail",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
        },
    )
    notification_id = create_resp.json()["id"]

    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> bool:
        raise ConnectionError("dns failure")

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )

    response = await api_client.post(
        f"/api/v3/notification/{notification_id}/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_message"]
    assert "ConnectionError" in body["error_message"]


@pytest.mark.asyncio
async def test_test_endpoint_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """FR-024b: the test endpoint fires outbound HTTP — admin only."""
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login(api_client, "admin")
    create_resp = await api_client.post(
        "/api/v3/notification",
        json={
            "name": "guarded",
            "apprise_url": "discord://1234567890/abcdefghijklmnop",
        },
    )
    notification_id = create_resp.json()["id"]
    # Logout, log in as readonly.
    await api_client.post("/api/v3/auth/logout")
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _login(api_client, "reader")
    response = await api_client.post(
        f"/api/v3/notification/{notification_id}/test"
    )
    assert response.status_code == 403
