"""Pytest fixtures for the FastAPI app tests.

Each test gets:
  - a fresh in-memory SQLite database with all tables created
  - a FastAPI app wired to that database
  - an ``httpx.AsyncClient`` for ASGI calls
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from romarr.api.app import create_app

# Importing the models modules registers their tables on Base.metadata.
from romarr.auth import models as _auth_models  # noqa: F401
from romarr.db.session import create_engine
from romarr.domain import Base
from romarr.domain import models as _domain_models  # noqa: F401


@pytest_asyncio.fixture
async def api_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine used by both the API tests and their app."""
    # ``StaticPool`` would let multiple connections share a memory DB,
    # but FastAPI's lifespan + per-request session pattern works fine
    # against a single shared connection. We use a unique URL per
    # test to avoid cross-test bleed.
    engine = create_engine(
        "sqlite+aiosqlite:///:memory:?cache=shared",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(api_engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    """httpx.AsyncClient wired to a FastAPI app over the same engine."""
    app = create_app()

    # Override the lifespan-built engine + sessionmaker with the
    # in-memory one we already initialized — this keeps the schema
    # alive across requests and avoids a redundant create_all().
    from sqlalchemy.ext.asyncio import async_sessionmaker

    app.state.db_engine = api_engine
    app.state.db_sessionmaker = async_sessionmaker(api_engine, expire_on_commit=False)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
