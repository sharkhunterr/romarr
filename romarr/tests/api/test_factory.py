"""Application factory tests (T007, T008, T009).

The factory composes the FastAPI app and wires:

  * the documented title / version / description / docs URLs (T007);
  * the spec 012 Tasks subsystem on lifespan startup when
    ``app.state._enable_scheduler = True`` is set (T008);
  * the four-phase :func:`graceful_shutdown` protocol on lifespan
    exit, ensuring the scheduler is stopped before the engine is
    disposed (T009).

The forward-looking pieces from T010's enumeration (watcher /
heartbeat / health-engine startup, MW middleware, bridge
routers, WebSocket handler, OpenAPI customiser) are wired
in subsequent phases. The tests below cover what's wireable
today.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

import romarr
from romarr.api import create_app
from romarr.api.factory import create_app as create_app_from_factory
from romarr.domain import Base


@pytest.fixture
def fresh_app_db(tmp_path: Path) -> Iterator[str]:
    """Tmp SQLite file with the full schema applied — production
    Alembic equivalent. The lifespan-wired scheduler issues
    ``SELECT * FROM job WHERE enabled = 1`` on startup; without
    the schema in place that would crash before we could check
    the wiring."""
    db_path = tmp_path / "factory.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    async def _bootstrap() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_bootstrap())
    yield url


# ---------------------------------------------------------------------------
# T007 — create_app builds the documented FastAPI shape
# ---------------------------------------------------------------------------


def test_creates_app_returns_fastapi_with_documented_shape() -> None:
    app = create_app()
    assert app.title == "Romarr"
    assert app.description == "Self-hosted ROM acquisition manager"
    # Version mirrors the package version so /api/v3/system/status
    # round-trips it.
    assert app.version == romarr.__version__
    # Spec 013 mandates /api/v3 docs URLs.
    assert app.docs_url == "/api/v3/docs"
    assert app.redoc_url == "/api/v3/redoc"
    assert app.openapi_url == "/api/v3/openapi.json"


def test_factory_module_reexports_create_app() -> None:
    """``romarr.api.factory.create_app`` is the spec-canonical
    import path. It must be the same callable as
    ``romarr.api.create_app`` so tests / docs can use either
    interchangeably."""
    assert create_app_from_factory is create_app


# ---------------------------------------------------------------------------
# T008 — lifespan startup wires the scheduler when opt-in is set
# ---------------------------------------------------------------------------


def test_lifespan_starts_scheduler_when_enabled(
    fresh_app_db: str,
) -> None:
    """``app.state._enable_scheduler = True`` causes the lifespan
    startup to build a :class:`SchedulerService` and a
    :class:`CancellationRegistry` and store them on
    ``app.state``."""
    app = create_app(database_url=fresh_app_db)
    app.state._enable_scheduler = True

    with TestClient(app):
        scheduler = app.state.scheduler
        assert scheduler is not None
        assert scheduler._started is True
        cancellation_registry = app.state.cancellation_registry
        assert cancellation_registry is not None


def test_lifespan_skips_scheduler_when_default(
    fresh_app_db: str,
) -> None:
    """Default OFF — the test suite builds the app many times
    and shouldn't pay the SchedulerService bootstrap cost
    unless the test explicitly opts in."""
    app = create_app(database_url=fresh_app_db)
    # No _enable_scheduler attribute set.

    with TestClient(app):
        # Scheduler is not on app.state when disabled.
        assert getattr(app.state, "scheduler", None) is None
        assert getattr(app.state, "cancellation_registry", None) is None


# ---------------------------------------------------------------------------
# T009 — lifespan shutdown runs graceful_shutdown
# ---------------------------------------------------------------------------


def test_lifespan_shutdown_stops_scheduler(
    fresh_app_db: str,
) -> None:
    """Exiting the lifespan triggers the four-phase
    :func:`graceful_shutdown` protocol (FR-021); the
    scheduler's ``_started`` flag flips back to False so the
    application loop exits cleanly. Once shutdown has run, the
    scheduler reference still exists on ``app.state`` (we don't
    null it out), but it's no longer accepting new work."""
    app = create_app(database_url=fresh_app_db)
    app.state._enable_scheduler = True

    with TestClient(app):
        scheduler_ref = app.state.scheduler
        assert scheduler_ref._started is True

    # After exiting the lifespan, scheduler.stop() ran.
    assert scheduler_ref._started is False
