"""Admin user-CRUD endpoint tests — /api/v3/user/*."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_USER,
    User,
    hash_password,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    engine: AsyncEngine,
    *,
    username: str,
    role: str,
    is_active: bool = True,
    password: str = "goodpassword",
) -> User:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        u = User(
            username=username,
            role=role,
            is_active=is_active,
            hashed_password=hash_password(password),
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
    return u


async def _login_as(
    client: httpx.AsyncClient, *, username: str, password: str = "goodpassword"
) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_endpoints_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/user")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_endpoints_non_admin_returns_403(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="alice")

    response = await api_client.get("/api/v3/user")
    assert response.status_code == 403
    assert response.json()["errorCode"] == "permission_denied"


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_list_users(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="admin")

    response = await api_client.get("/api/v3/user")
    assert response.status_code == 200
    usernames = {u["username"] for u in response.json()}
    assert {"admin", "alice"}.issubset(usernames)
    assert "system" not in usernames  # id=0 sentinel hidden


@pytest.mark.asyncio
async def test_admin_creates_and_reads_user(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")

    create = await api_client.post(
        "/api/v3/user",
        json={
            "username": "bob",
            "password": "supersecret123",
            "email": "bob@example.com",
            "role": "user",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["username"] == "bob"
    assert body["role"] == "user"
    user_id = body["id"]

    read = await api_client.get(f"/api/v3/user/{user_id}")
    assert read.status_code == 200
    assert read.json()["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_admin_creates_user_duplicate_username_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="admin")

    response = await api_client.post(
        "/api/v3/user",
        json={"username": "alice", "password": "supersecret123"},
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "username_taken"


@pytest.mark.asyncio
async def test_admin_creates_oidc_only_user_without_password(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")

    response = await api_client.post(
        "/api/v3/user",
        json={"username": "oidc_user", "role": "user"},
    )
    assert response.status_code == 201
    assert response.json()["username"] == "oidc_user"


@pytest.mark.asyncio
async def test_admin_updates_role(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    target = await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="admin")

    response = await api_client.put(
        f"/api/v3/user/{target.id}",
        json={"role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_cannot_demote_lone_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    admin = await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")

    response = await api_client.put(
        f"/api/v3/user/{admin.id}",
        json={"role": "user"},
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "cannot_delete_last_admin"


@pytest.mark.asyncio
async def test_admin_can_demote_when_other_admin_exists(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    admin1 = await _seed_user(api_engine, username="admin1", role=ROLE_ADMIN)
    await _seed_user(api_engine, username="admin2", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin1")

    response = await api_client.put(
        f"/api/v3/user/{admin1.id}",
        json={"role": "user"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "user"


@pytest.mark.asyncio
async def test_admin_deletes_user(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    target = await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="admin")

    response = await api_client.delete(f"/api/v3/user/{target.id}")
    assert response.status_code == 204

    # Subsequent read 404s.
    miss = await api_client.get(f"/api/v3/user/{target.id}")
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_delete_lone_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    admin = await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")

    response = await api_client.delete(f"/api/v3/user/{admin.id}")
    assert response.status_code == 409
    assert response.json()["errorCode"] == "cannot_delete_last_admin"


@pytest.mark.asyncio
async def test_admin_cannot_delete_system_sentinel(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The id=0 system sentinel must never be removable."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                id=0,
                username="system",
                role=ROLE_ADMIN,
                is_active=False,
                hashed_password=None,
            )
        )
        await session.commit()
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")

    # Hidden from the public read surface.
    miss = await api_client.get("/api/v3/user/0")
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_admin_deactivates_user_revokes_their_sessions(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    target = await _seed_user(api_engine, username="alice", role=ROLE_USER)

    # Alice logs in on her own client.
    other_client = httpx.AsyncClient(
        transport=api_client._transport, base_url="http://test"
    )
    await _login_as(other_client, username="alice")
    assert (await other_client.get("/api/v3/auth/me")).status_code == 200

    # Admin deactivates her.
    await _login_as(api_client, username="admin")
    response = await api_client.put(
        f"/api/v3/user/{target.id}", json={"is_active": False}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Alice's session was revoked.
    me = await other_client.get("/api/v3/auth/me")
    assert me.status_code == 401
    await other_client.aclose()


@pytest.mark.asyncio
async def test_admin_reset_password_returns_one_time_token(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    target = await _seed_user(api_engine, username="alice", role=ROLE_USER)
    await _login_as(api_client, username="admin")

    response = await api_client.post(f"/api/v3/user/{target.id}/reset-password")
    assert response.status_code == 201
    body = response.json()
    assert body["plaintext"]
    assert "expires_at" in body


@pytest.mark.asyncio
async def test_admin_reset_password_unknown_user_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _login_as(api_client, username="admin")
    response = await api_client.post("/api/v3/user/9999/reset-password")
    assert response.status_code == 404
