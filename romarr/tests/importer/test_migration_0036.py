"""Migration 0036 — ``import_history.size_bytes``.

Asserts the new BigInteger column lands on upgrade and goes away
on downgrade. The column is NULLable so historical rows survive
without backfill — the orchestrator populates it from the
hash-step ``size_bytes`` local var on every subsequent import.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config(db_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "src/romarr/db/alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, tuple[str, int]]:
    """Return ``{column: (type, notnull)}`` from ``PRAGMA table_info``."""
    return {
        row[1]: (row[2], row[3])
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def test_migration_0036_adds_size_bytes(tmp_path: Path) -> None:
    db = tmp_path / "test_0036.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cols = _columns(conn, "import_history")
        assert "size_bytes" in cols
        col_type, notnull = cols["size_bytes"]
        # BIGINT in SQLite renders as either ``BIGINT`` or
        # ``BIGINTEGER`` depending on the alembic batch; accept
        # both as long as the column is NULLable.
        assert "BIG" in col_type.upper() or "INT" in col_type.upper()
        assert notnull == 0, "size_bytes must be NULLable (no backfill)"
    finally:
        conn.close()


def test_migration_0036_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "test_0036_rev.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0035_quality_profile_auto_grab_min_score")

    conn = sqlite3.connect(db)
    try:
        cols = _columns(conn, "import_history")
        assert "size_bytes" not in cols
    finally:
        conn.close()
