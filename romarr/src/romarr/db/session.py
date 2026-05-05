"""Async SQLAlchemy engine + session factory.

A single engine and sessionmaker are cached per process. Tests that
need a fresh in-memory database call :func:`create_engine` directly
with their own URL.

SQLite-specific note: SQLite ships with foreign-key enforcement DISABLED
by default. Romarr's domain depends on cascade rules (FR-002, FR-005),
so this module attaches a connection-level listener that issues
``PRAGMA foreign_keys=ON`` on every new SQLite connection.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from romarr.config import get_settings


def _enable_sqlite_fk(dbapi_connection: Any, _connection_record: Any) -> None:
    """Per-connection SQLite hardening pragmas:

    * ``foreign_keys=ON`` — Romarr's domain depends on cascade rules
      (FR-002, FR-005) which SQLite disables by default.
    * ``journal_mode=WAL`` — concurrent readers + one writer without
      whole-database locks. The bootstrap path (seed defaults +
      platform pack + setup token) runs three near-simultaneous
      transactions; without WAL it hits ``database is locked``.
    * ``busy_timeout=5000`` — when a writer holds the lock, queue
      pending writers up to 5 s instead of failing immediately.
    * ``synchronous=NORMAL`` — safe under WAL and noticeably faster
      than the FULL default for the bootstrap workload.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_engine(database_url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    """Build a fresh async engine.

    ``database_url`` defaults to ``Settings.database_url``. Tests use
    explicit URLs (``sqlite+aiosqlite:///:memory:``) instead of the
    cached default.

    For SQLite URLs, this attaches a ``PRAGMA foreign_keys=ON`` listener
    so cascade rules are honoured at runtime.
    """
    url = database_url or get_settings().database_url
    engine = create_async_engine(url, echo=echo, future=True)
    if url.startswith(("sqlite", "sqlite+")):
        event.listens_for(engine.sync_engine, "connect")(_enable_sqlite_fk)
    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build an async sessionmaker bound to ``engine``."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, building it on first use."""
    return create_engine()


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async sessionmaker."""
    return create_sessionmaker(get_engine())
