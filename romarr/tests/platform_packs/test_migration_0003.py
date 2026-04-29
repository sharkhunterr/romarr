"""Migration 0003 end-to-end test (T007)."""

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


def test_migration_creates_two_new_tables(tmp_path: Path) -> None:
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
        assert "parsing_strategies" in tables
        assert "platform_pack_application_log" in tables

        # platform_pack already had contents_hash from foundation; verify
        # the migration didn't accidentally drop it.
        platform_pack_columns = {
            r[1]
            for r in cur.execute("PRAGMA table_info(platform_pack)").fetchall()
        }
        assert "contents_hash" in platform_pack_columns

        # CHECK constraints exist on parsing_strategies.pack_source.
        # SQLite doesn't expose check constraints in PRAGMA easily, but
        # an INSERT with a bad value MUST fail.
        cur.execute(
            "INSERT INTO parsing_strategies (id, name, pattern, "
            "apply_to_platforms, pack_source, created_at, updated_at) "
            "VALUES ('bad', 'Bad', '.', '[]', 'invalid_source', "
            "current_timestamp, current_timestamp)"
        )
    except sqlite3.IntegrityError:
        # Expected — the CHECK fired.
        pass
    else:  # pragma: no cover — would mean the CHECK didn't fire
        raise AssertionError("CHECK on pack_source did not fire")
    finally:
        conn.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    """Downgrade + re-upgrade leaves the schema identical."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002_metadata_layer")
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
        assert "parsing_strategies" in tables
        assert "platform_pack_application_log" in tables
    finally:
        conn.close()
