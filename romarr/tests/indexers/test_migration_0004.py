"""Migration 0004 end-to-end test (T011)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config(db_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(repo_root / "src/romarr/db/alembic")
    )
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_creates_indexer_and_application(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        }
        assert "indexer" in tables
        assert "application" in tables

        # download_client_id exists with no FK (the FK arrives in spec 005).
        idx_columns = {
            r[1]: r for r in cur.execute("PRAGMA table_info(indexer)").fetchall()
        }
        assert "download_client_id" in idx_columns
        fks = list(cur.execute("PRAGMA foreign_key_list(indexer)"))
        assert all(fk[3] != "download_client_id" for fk in fks)

        # CHECK constraint on implementation fires.
        try:
            cur.execute(
                "INSERT INTO indexer "
                "(name, implementation, url, categories, source, "
                "created_at, updated_at) VALUES "
                "('bad', 'not-real', 'https://x', '[]', 'manual', "
                "current_timestamp, current_timestamp)"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on implementation did not fire")
    finally:
        conn.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0003_platform_packs")
    command.upgrade(cfg, "head")
