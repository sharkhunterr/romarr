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

# Repo layout: ``src/romarr/db/migrations.py`` → repo root is
# three levels up. That holds when the package is run from a
# checkout. After ``pip install`` the file lives under
# ``site-packages/romarr/db/`` and the parent walk lands in
# Python's lib dir — no ``alembic.ini`` there. Fall back to
# the current working directory in that case (the Docker image
# COPYs ``alembic.ini`` to ``/app/`` and sets ``WORKDIR /app``).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INI = _REPO_ROOT / "alembic.ini"


def _resolve_ini() -> Path:
    if _DEFAULT_INI.is_file():
        return _DEFAULT_INI
    cwd_ini = Path.cwd() / "alembic.ini"
    if cwd_ini.is_file():
        return cwd_ini
    # Last-resort: bundled migrations directory has no ini, but
    # the package ships it next to ``alembic/`` for installed
    # builds. Final fallback returns ``_DEFAULT_INI`` so the
    # caller surfaces Alembic's own ``No 'script_location'``
    # error with a meaningful path in the message.
    return _DEFAULT_INI


def _build_config(database_url: str | None = None) -> Config:
    """Construct an Alembic ``Config`` rooted at the repo's
    ``alembic.ini``. ``database_url`` overrides the ini value
    so tests can target an in-memory engine."""
    cfg = Config(str(_resolve_ini()))
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
