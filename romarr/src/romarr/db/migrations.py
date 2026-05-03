"""Alembic helpers — programmatic ``upgrade head`` / ``downgrade``.

Lets the FastAPI lifespan + the ``romarr migrate`` CLI both
drive the same code path. Operators who prefer the canonical
``alembic`` CLI can keep using it; the helpers in this module
just expose the same operations through Python so the
container entrypoint doesn't need to shell out.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

# Repo layout: src/romarr/db/migrations.py → repo root is two
# levels up from this file (src/romarr/db) and then once more
# to reach the project root that owns alembic.ini.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INI = _REPO_ROOT / "alembic.ini"


def _build_config(database_url: str | None = None) -> Config:
    """Construct an Alembic ``Config`` rooted at the repo's
    ``alembic.ini``. ``database_url`` overrides the ini value
    so tests can target an in-memory engine."""
    cfg = Config(str(_DEFAULT_INI))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def upgrade_head_sync(database_url: str | None = None) -> None:
    """Run ``alembic upgrade head`` synchronously.

    Safe to call from inside a running event loop — Alembic
    drives its own connection so the surrounding asyncio loop
    isn't disturbed. ``database_url`` is passed through to the
    Alembic config; ``None`` means "use whatever ``alembic.ini``
    declares" (typically the SQLite default).
    """
    cfg = _build_config(database_url)
    command.upgrade(cfg, "head")


def downgrade_sync(target: str, database_url: str | None = None) -> None:
    """Run ``alembic downgrade <target>`` synchronously."""
    cfg = _build_config(database_url)
    command.downgrade(cfg, target)


__all__ = ["downgrade_sync", "upgrade_head_sync"]
