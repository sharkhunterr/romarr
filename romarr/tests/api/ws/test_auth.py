"""WebSocket auth tests (T061, T062, T063, FR-018).

Exercises the on-upgrade auth resolver through FastAPI's
TestClient.websocket_connect. The handler accepts the upgrade
when the auth chain resolves a Principal (via api-key, cookie,
or bearer); rejects with WebSocket close code 1008 (policy
violation) otherwise.

These tests build the TestClient WITHOUT entering its context
manager — the lifespan would otherwise create a fresh engine
on ``app.state`` and overwrite the test engine we just set.
``websocket_connect`` doesn't need lifespan to be active.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.websockets import WebSocketDisconnect

from romarr.api import create_app
from romarr.auth import ROLE_ADMIN, User, hash_api_key, hash_password
from romarr.auth.models import ApiKey


async def _seed_admin_with_api_key(engine: AsyncEngine) -> str:
    """Insert an admin user + API key. Returns the plaintext."""
    plaintext = "rmk_test_ws_auth"
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        user = User(
            username="ws-admin",
            role=ROLE_ADMIN,
            is_active=True,
            hashed_password=hash_password("goodpassword"),
        )
        session.add(user)
        await session.flush()
        session.add(
            ApiKey(
                user_id=user.id,
                name="ws-test",
                key_prefix=plaintext[:8],
                key_hash=hash_api_key(plaintext),
                scopes=["read"],
            )
        )
        await session.commit()
    return plaintext


def _build_sync_client(engine: AsyncEngine) -> TestClient:
    """Build a fresh app + sync TestClient over the test engine.

    Returns the TestClient WITHOUT entering its context manager
    — that would fire the lifespan, which builds its own fresh
    engine on app.state and overwrites the one we just stamped.
    websocket_connect doesn't need lifespan to be active; the
    sessionmaker stays as we set it."""
    app = create_app()
    sm = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sm
    return TestClient(app)


# ---------------------------------------------------------------------------
# T061 — apikey query param
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apikey_query_param_upgrades_succeeds(
    api_engine: AsyncEngine,
) -> None:
    plaintext = await _seed_admin_with_api_key(api_engine)
    client = _build_sync_client(api_engine)
    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws:
        welcome = ws.receive_json()
        assert welcome["messageType"] == "systemMessage"
        assert welcome["data"]["kind"] == "welcome"
        assert welcome["data"]["username"] == "ws-admin"
        assert "connectionId" in welcome["data"]


@pytest.mark.asyncio
async def test_apikey_header_upgrade_succeeds(
    api_engine: AsyncEngine,
) -> None:
    plaintext = await _seed_admin_with_api_key(api_engine)
    client = _build_sync_client(api_engine)
    with client.websocket_connect(
        "/signalr/messages",
        headers={"X-Api-Key": plaintext},
    ) as ws:
        welcome = ws.receive_json()
        assert welcome["messageType"] == "systemMessage"


# ---------------------------------------------------------------------------
# T062 — cookie session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cookie_session_upgrade_succeeds(
    api_engine: AsyncEngine,
) -> None:
    """Login via REST → reuse cookie on WS upgrade."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="cookie-user",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()

    client = _build_sync_client(api_engine)
    login = client.post(
        "/api/v3/auth/login",
        json={
            "username": "cookie-user",
            "password": "goodpassword",
        },
    )
    assert login.status_code == 204

    with client.websocket_connect("/signalr/messages") as ws:
        welcome = ws.receive_json()
        assert welcome["messageType"] == "systemMessage"
        assert welcome["data"]["username"] == "cookie-user"


# ---------------------------------------------------------------------------
# T063 — unauthenticated upgrade rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauth_upgrade_rejected(
    api_engine: AsyncEngine,
) -> None:
    """No api-key, no cookie, no bearer → policy-violation
    close (1008) before the welcome frame ships."""
    client = _build_sync_client(api_engine)
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
        "/signalr/messages"
    ) as ws:
        ws.receive_json()
    assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_invalid_apikey_rejected(
    api_engine: AsyncEngine,
) -> None:
    """A bogus apikey resolves to no principal — same outcome
    as no-credentials."""
    client = _build_sync_client(api_engine)
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
        "/signalr/messages?apikey=rmk_does_not_exist"
    ) as ws:
        ws.receive_json()
    assert exc_info.value.code == 1008


# ---------------------------------------------------------------------------
# Roundtrip: client ping → server pong
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_ping_receives_pong(
    api_engine: AsyncEngine,
) -> None:
    """The handler treats any received frame as a keepalive
    ping and echoes a systemMessage pong."""
    plaintext = await _seed_admin_with_api_key(api_engine)
    client = _build_sync_client(api_engine)
    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws:
        ws.receive_json()  # consume welcome
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["messageType"] == "systemMessage"
        assert pong["data"]["kind"] == "pong"
