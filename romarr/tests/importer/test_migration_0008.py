"""Spec 008 migration test — apply 0008_import_pipeline to a fresh DB.

Asserts the import_history table + its FKs land, plus the three
new columns on unidentified_dump (``rejection_reason``,
``library_id``, ``suggested_game_id``). The library FK on
``unidentified_dump.library_id`` is gated on the ``library``
table existing — since spec 009 ships before spec 008 in the
project's migration chain, the library table DOES exist when
0008 runs and the FK is finalised here.
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


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [
        (row[2], row[4])
        for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    ]


def test_migration_creates_import_history_table(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        }
        assert "import_history" in tables

        # FKs land on every nullable target.
        fks = _foreign_keys(conn, "import_history")
        targets = {pair[0] for pair in fks}
        assert {"download_client", "game", "release", "dump"} <= targets
    finally:
        conn.close()


def test_migration_extends_unidentified_dump(tmp_path: Path) -> None:
    db = tmp_path / "test_extends.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cols = _columns(conn, "unidentified_dump")
        assert {"rejection_reason", "library_id", "suggested_game_id"} <= cols

        # FKs: suggested_game_id → game (always); library_id → library
        # (because spec 009 already shipped, the gated FK lands here).
        fks = _foreign_keys(conn, "unidentified_dump")
        targets = {pair[0] for pair in fks}
        assert "game" in targets
        assert "library" in targets
    finally:
        conn.close()


def test_migration_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "test_reversible.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0009_libraries")

    conn = sqlite3.connect(db)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        }
        assert "import_history" not in tables

        # The three columns are dropped from unidentified_dump.
        cols = _columns(conn, "unidentified_dump")
        assert "rejection_reason" not in cols
        assert "library_id" not in cols
        assert "suggested_game_id" not in cols
    finally:
        conn.close()
