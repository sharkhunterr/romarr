"""Spec 009 migration test — apply 0009_libraries to a fresh DB.

Two assertions:

  1. After ``alembic upgrade head``, the ``library`` table, the
     ``library_platform`` m2m, and the new ``release.library_id``
     FK are all present.
  2. The migration finalises ``library_custom_format.library_id``'s
     FK target — that column was created NOT NULL by spec 006 but
     without an FK target.
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


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """Return ``(referenced_table, referenced_column)`` per FK on ``table``."""
    return [
        (row[2], row[4])
        for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    ]


def test_migration_creates_library_table_and_release_fk(tmp_path: Path) -> None:
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
        assert "library" in tables
        assert "library_platform" in tables

        # release.library_id column exists with FK to library(id).
        release_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(release)").fetchall()
        }
        assert "library_id" in release_columns
        release_fks = _foreign_keys(conn, "release")
        assert ("library", "id") in release_fks

        # library_custom_format.library_id FK now points to library.
        lcf_fks = _foreign_keys(conn, "library_custom_format")
        assert ("library", "id") in lcf_fks
    finally:
        conn.close()


def test_migration_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "test_reversible.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    conn = sqlite3.connect(db)
    try:
        tables = sorted(
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        )
        assert tables == []
    finally:
        conn.close()


def test_migration_unidentified_dump_finalisation_gate_no_ops_at_0009(
    tmp_path: Path,
) -> None:
    """0009's ``unidentified_dump.library_id`` finalisation branch
    must be a no-op when the column does not yet exist.

    Spec 008 adds the column and ships AFTER spec 009 in the
    project's migration chain (down_revision = 0009_libraries),
    so when 0009 runs ``unidentified_dump.library_id`` doesn't
    exist yet. Stopping the upgrade exactly at 0009 exercises the
    gated branch.
    """
    db = tmp_path / "test_at_0009.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")

    # Stop the upgrade at 0009; do NOT roll forward into 0008.
    command.upgrade(cfg, "0009_libraries")

    conn = sqlite3.connect(db)
    try:
        # 0009 ran but 0008 hasn't; the column doesn't exist yet
        # and 0009's gated branch silently skipped the FK.
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(unidentified_dump)")
        }
        assert "library_id" not in columns

        # Pulling forward to 0008 (head) materialises the column +
        # FK via 0008's unconditional path.
        command.upgrade(cfg, "head")
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(unidentified_dump)")
        }
        assert "library_id" in columns
        ud_fks = _foreign_keys(conn, "unidentified_dump")
        assert ("library", "id") in ud_fks
    finally:
        conn.close()
