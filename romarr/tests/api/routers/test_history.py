"""Unified history router tests (T047, T048, FR-014).

Seeds rows into all three audit tables (import_history,
search_history, job_run) and exercises:

  * the canonical pagination envelope on GET /api/v3/history;
  * the synthesised ``eventType`` discriminator;
  * the ``successful`` derivation per source-table semantics;
  * the ``/since`` filter against ``date >= since``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.importer.models import ImportHistory
from romarr.search.models import SearchHistory
from romarr.tasks.models import Job, JobRun
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_three_event_kinds(engine: AsyncEngine) -> None:
    """Seed one row in each of the three audit tables, with
    monotonically increasing started_at timestamps so the date
    sort is deterministic."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    base = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    async with sm() as session:
        # Job parent — JobRun has a CASCADE FK on job.id.
        session.add(
            Job(
                id="MissingSearch",
                name="Missing Search",
                type="missing_search",
                schedule_interval_seconds=3600,
            )
        )
        await session.flush()

        session.add(
            ImportHistory(
                source_path="/in/foo.zip",
                imported_via="manual",
                success=True,
                correlation_id=str(uuid4()),
                started_at=base,
            )
        )
        session.add(
            SearchHistory(
                search_type="manual",
                results_count=5,
                started_at=base + timedelta(minutes=10),
                correlation_id=str(uuid4()),
            )
        )
        session.add(
            JobRun(
                job_id="MissingSearch",
                started_at=base + timedelta(minutes=20),
                status="success",
                triggered_by="manual",
            )
        )
        await session.commit()


@pytest.fixture
async def authed_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


# ---------------------------------------------------------------------------
# T047 — paginated history with all three event types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginated_history_unions_all_three_tables(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """One row in each of import_history / search_history /
    job_run produces three entries in the unified feed,
    discriminated by ``eventType``."""
    await _seed_three_event_kinds(api_engine)

    resp = await authed_client.get(
        "/api/v3/history?sortKey=date&sortDirection=asc"
    )
    assert resp.status_code == 200
    body = resp.json()

    # Canonical envelope.
    assert body["totalRecords"] == 3
    assert body["page"] == 1
    assert len(body["records"]) == 3

    event_types = [r["eventType"] for r in body["records"]]
    assert event_types == ["import", "search", "job_run"]

    # Sonarr-shape camelCase keys present on every record.
    for record in body["records"]:
        assert {"eventType", "id", "date", "successful"}.issubset(
            record.keys()
        )

    # ``successful`` derivation per source semantics.
    by_type = {r["eventType"]: r for r in body["records"]}
    assert by_type["import"]["successful"] is True
    # SearchHistory.results_count > 0 → true
    assert by_type["search"]["successful"] is True
    # JobRun.status == "success" → true
    assert by_type["job_run"]["successful"] is True


@pytest.mark.asyncio
async def test_search_with_zero_results_marks_unsuccessful(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """``SearchHistory.results_count > 0`` is the success
    derivation — a search returning zero results shows up as
    ``successful=false``."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            SearchHistory(
                search_type="rss",
                results_count=0,
                started_at=datetime.now(UTC),
                correlation_id=str(uuid4()),
            )
        )
        await session.commit()

    resp = await authed_client.get("/api/v3/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["successful"] is False


@pytest.mark.asyncio
async def test_failed_import_marks_unsuccessful(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """``ImportHistory.success=False`` flows through to
    ``successful=false``."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            ImportHistory(
                source_path="/in/broken.zip",
                imported_via="automatic",
                success=False,
                error_msg="fixture failure",
                correlation_id=str(uuid4()),
                started_at=datetime.now(UTC),
            )
        )
        await session.commit()

    resp = await authed_client.get("/api/v3/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["records"][0]["successful"] is False


# ---------------------------------------------------------------------------
# T048 — /since filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_since_filters_to_events_after_threshold(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Three events seeded at 12:00, 12:10, 12:20. ``?since=12:15``
    returns only the 12:20 row."""
    await _seed_three_event_kinds(api_engine)

    threshold = datetime(2026, 4, 30, 12, 15, 0, tzinfo=UTC)
    resp = await authed_client.get(
        "/api/v3/history/since",
        params={"date": threshold.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["eventType"] == "job_run"


@pytest.mark.asyncio
async def test_since_returns_all_when_threshold_in_past(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await _seed_three_event_kinds(api_engine)
    threshold = datetime(2025, 1, 1, tzinfo=UTC)
    resp = await authed_client.get(
        "/api/v3/history/since",
        params={"date": threshold.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["totalRecords"] == 3


# ---------------------------------------------------------------------------
# Empty + auth + invalid sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_history_returns_zero_records(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 0
    assert body["records"] == []


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/history")
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_invalid_sort_key_returns_400(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get(
        "/api/v3/history?sortKey=NotARealField"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_sort_key"
