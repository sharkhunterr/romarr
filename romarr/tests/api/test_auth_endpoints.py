"""End-to-end tests for /api/v3/auth/*."""

from __future__ import annotations

import secrets

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import (
    ROLE_ADMIN,
    SESSION_COOKIE_NAME,
    SetupToken,
    User,
    hash_api_key,
    hash_password,
    maybe_bootstrap_setup_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_admin_user(engine: AsyncEngine, *, password: str = "goodpassword") -> User:
    """Bypass the setup flow and drop a ready-to-use admin in the DB."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        u = User(
            username="alice",
            role=ROLE_ADMIN,
            is_active=True,
            hashed_password=hash_password(password),
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_creates_first_admin_and_logs_in(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        bootstrap = await maybe_bootstrap_setup_token(session)
    assert bootstrap.plaintext is not None

    response = await api_client.post(
        "/api/v3/auth/setup",
        json={"username": "root", "password": "supersecret123"},
        headers={"X-Setup-Token": bootstrap.plaintext},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "root"
    assert body["user"]["role"] == "admin"
    # Auto-login: the response set a session cookie.
    assert SESSION_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_setup_replay_rejected(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        bootstrap = await maybe_bootstrap_setup_token(session)
    assert bootstrap.plaintext is not None

    first = await api_client.post(
        "/api/v3/auth/setup",
        json={"username": "root", "password": "supersecret123"},
        headers={"X-Setup-Token": bootstrap.plaintext},
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v3/auth/setup",
        json={"username": "root2", "password": "supersecret123"},
        headers={"X-Setup-Token": bootstrap.plaintext},
    )
    assert second.status_code == 401
    assert second.json()["errorCode"] == "setup_already_completed"


@pytest.mark.asyncio
async def test_setup_wrong_token_rejected(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        await maybe_bootstrap_setup_token(session)

    response = await api_client.post(
        "/api/v3/auth/setup",
        json={"username": "root", "password": "supersecret123"},
        headers={"X-Setup-Token": "completely-wrong"},
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "setup_token_invalid"


# ---------------------------------------------------------------------------
# /login + /logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_sets_cookie_and_logout_clears_it(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)

    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert response.status_code == 204
    assert SESSION_COOKIE_NAME in response.cookies

    # The cookie carries HttpOnly + SameSite=Lax + Max-Age (no Secure
    # because the test transport reports scheme=http).
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=" in set_cookie
    assert "secure" not in set_cookie

    # Logout clears the cookie.
    logout = await api_client.post("/api/v3/auth/logout")
    assert logout.status_code == 204


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401_uniform_envelope(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "WRONG"},
    )
    assert response.status_code == 401
    body = response.json()
    # FR-023: never disclose which method failed.
    assert body["errorMessage"] == "unauthenticated"
    assert body["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_login_unknown_user_returns_same_401_envelope(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_login_rate_limit_kicks_in_after_10_attempts(
    api_client: httpx.AsyncClient,
) -> None:
    # No user → every attempt fails 401, but the rate limiter counts
    # all 10. The 11th gets 429 BEFORE bcrypt runs.
    headers = {"X-Forwarded-For": "203.0.113.7"}  # deterministic IP
    for _ in range(10):
        await api_client.post(
            "/api/v3/auth/login",
            json={"username": "anyone", "password": "x"},
            headers=headers,
        )
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "anyone", "password": "x"},
        headers=headers,
    )
    assert response.status_code == 429
    assert response.headers.get("Retry-After") is not None
    assert response.json()["errorCode"] == "rate_limited"


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/auth/me")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_get_me_with_session_cookie(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204

    me = await api_client.get("/api/v3/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert me.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_put_me_changes_password_revokes_other_sessions(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )

    update = await api_client.put(
        "/api/v3/auth/me",
        json={"password": "newpassword456"},
    )
    assert update.status_code == 200

    # Old session was revoked along with every other session for this
    # user (the request that did the update returns its own
    # short-circuit-OK path; subsequent calls without re-login fail).
    response = await api_client.get("/api/v3/auth/me")
    assert response.status_code == 401

    # Re-login with the new password works.
    relogin = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "newpassword456"},
    )
    assert relogin.status_code == 204


# ---------------------------------------------------------------------------
# /api-key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_use_api_key(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )

    create = await api_client.post(
        "/api/v3/auth/api-key",
        json={"name": "Notifiarr", "scopes": ["read", "write"]},
    )
    assert create.status_code == 201
    body = create.json()
    plaintext = body["plaintext"]
    assert plaintext.startswith("rmk_")
    assert set(body["scopes"]) == {"read", "write"}
    assert body["key_prefix"]

    # The plaintext authenticates a fresh request via X-Api-Key.
    fresh_client = httpx.AsyncClient(
        transport=api_client._transport, base_url="http://test"
    )
    me = await fresh_client.get(
        "/api/v3/auth/me", headers={"X-Api-Key": plaintext}
    )
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    await fresh_client.aclose()


@pytest.mark.asyncio
async def test_list_api_keys_does_not_expose_plaintext(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    await api_client.post(
        "/api/v3/auth/api-key", json={"name": "K1"}
    )
    await api_client.post(
        "/api/v3/auth/api-key", json={"name": "K2"}
    )
    response = await api_client.get("/api/v3/auth/api-key")
    assert response.status_code == 200
    rows = response.json()
    assert {r["name"] for r in rows} == {"K1", "K2"}
    for row in rows:
        assert "plaintext" not in row  # never re-shown


@pytest.mark.asyncio
async def test_create_api_key_with_unknown_scope_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    response = await api_client.post(
        "/api/v3/auth/api-key",
        json={"name": "K", "scopes": ["godmode"]},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "validation_failed"


@pytest.mark.asyncio
async def test_revoke_api_key_blocks_subsequent_use(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    create = await api_client.post(
        "/api/v3/auth/api-key", json={"name": "K"}
    )
    plaintext = create.json()["plaintext"]
    api_key_id = create.json()["id"]

    revoke = await api_client.delete(f"/api/v3/auth/api-key/{api_key_id}")
    assert revoke.status_code == 204

    # The plaintext no longer authenticates.
    await api_client.get(
        "/api/v3/auth/me",
        headers={
            "X-Api-Key": plaintext,
            "Cookie": "",  # also drop the session cookie
        },
        cookies={},  # clear cookie jar for this call
    )
    # Without a session cookie AND with a revoked key → 401.
    # The session cookie from login is still on the client — we
    # expect the X-Api-Key chain step to fail and fall through to
    # the cookie which DOES authenticate. So this assertion is
    # softer: confirm only that the revoked key alone wouldn't work.
    fresh = httpx.AsyncClient(
        transport=api_client._transport, base_url="http://test"
    )
    no_session = await fresh.get(
        "/api/v3/auth/me", headers={"X-Api-Key": plaintext}
    )
    assert no_session.status_code == 401
    await fresh.aclose()


@pytest.mark.asyncio
async def test_delete_someone_elses_api_key_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Per the router: same 404 for "doesn't exist" and "not yours"."""
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    response = await api_client.delete("/api/v3/auth/api-key/9999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auth chain — query-param API key + cookie precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apikey_query_param_authenticates(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    create = await api_client.post(
        "/api/v3/auth/api-key", json={"name": "Q"}
    )
    plaintext = create.json()["plaintext"]

    fresh = httpx.AsyncClient(
        transport=api_client._transport, base_url="http://test"
    )
    me = await fresh.get(f"/api/v3/auth/me?apikey={plaintext}")
    assert me.status_code == 200
    await fresh.aclose()


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_returns_app_info(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "romarr"


@pytest.mark.asyncio
async def test_openapi_schema_served(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v3/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v3/auth/login" in schema["paths"]
    assert "/api/v3/auth/me" in schema["paths"]


# Suppress unused-import warnings for tokens / users used inline.
_ = secrets
_ = hash_api_key
_ = SetupToken
_ = select
