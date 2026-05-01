"""Shared pytest fixtures.

The default ``async_session`` fixture spins up an in-memory SQLite
database with the full foundation schema applied (bypassing Alembic
for speed — Alembic is exercised separately by the migration test).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Importing the models module ensures every model class is registered
# with the metadata before create_all runs. Each spec's models live
# under their own package — listing them here keeps a single
# Base.metadata that knows about every table the test suite needs.
from romarr.api.app import create_app
from romarr.auth import models as _auth_models  # noqa: F401
from romarr.db.session import create_engine, create_sessionmaker
from romarr.domain import (
    Base,
    models,  # noqa: F401
)
from romarr.downloaders import models as _downloader_models  # noqa: F401
from romarr.importer import models as _importer_models  # noqa: F401
from romarr.indexers import models as _indexer_models  # noqa: F401
from romarr.libraries import models as _library_models  # noqa: F401
from romarr.metadata import models as _metadata_models  # noqa: F401
from romarr.notifications import models as _notification_models  # noqa: F401
from romarr.platform_packs import models as _platform_pack_models  # noqa: F401
from romarr.profiles import models as _profile_models  # noqa: F401
from romarr.search import models as _search_models  # noqa: F401


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Build a fresh in-memory SQLite engine per-test."""
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_sessionmaker_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(async_engine)


@pytest_asyncio.fixture
async def async_session(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A fresh AsyncSession per-test — auto-rolls-back on teardown."""
    async with async_sessionmaker_factory() as session:
        yield session


@pytest_asyncio.fixture
async def api_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine used by both the API tests and their app."""
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
    app.state.db_engine = api_engine
    app.state.db_sessionmaker = async_sessionmaker(api_engine, expire_on_commit=False)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
