"""Health endpoint tests (T064/T065, FR-024a)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_READONLY, User, hash_password
from romarr.notifications.models import HealthCheck as HealthCheckRow


async def _seed_user(
    engine: AsyncEngine,
    *,
    username: str,
    role: str = ROLE_ADMIN,
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


async def _seed_health_rows(
    engine: AsyncEngine,
) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sm() as session:
        session.add(
            HealthCheckRow(
                component="db",
                status="ok",
                message="DB round-trip 0.001s",
                severity_changed_at=now,
                last_checked_at=now,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.add(
            HealthCheckRow(
                component="indexer:slow-tracker",
                status="warning",
                message="caps reachable, but slow",
                severity_changed_at=now,
                last_checked_at=now,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T064 — anonymous callers get only {status} (FR-024a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_health_returns_status_only(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_health_rows(api_engine)
    response = await api_client.get("/api/v3/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "warning"}
    # No leakage of the per-component breakdown.
    assert "by_category" not in body
    assert "indexer:slow-tracker" not in str(body)


@pytest.mark.asyncio
async def test_unauthenticated_empty_db_returns_ok(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A fresh database with no health rows returns ok (no
    failure to report)."""
    response = await api_client.get("/api/v3/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# T065 — authenticated callers see the full breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_sees_full_breakdown(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    await _seed_health_rows(api_engine)

    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert login.status_code == 204

    response = await api_client.get("/api/v3/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warning"
    assert "by_category" in body
    assert "refreshed_at" in body
    # The per-component messages are visible.
    serialized = str(body)
    assert "slow-tracker" in serialized
    assert "caps reachable" in serialized


@pytest.mark.asyncio
async def test_readonly_user_also_sees_full_breakdown(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """FR-024a: any authenticated user (including readonly)
    sees the full breakdown — the tier is anon vs auth, not
    role-gated."""
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await _seed_health_rows(api_engine)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "reader", "password": "goodpassword"},
    )
    response = await api_client.get("/api/v3/health")
    assert response.status_code == 200
    body = response.json()
    assert "by_category" in body
