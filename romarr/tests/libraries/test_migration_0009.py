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


def test_migration_unidentified_dump_finalisation_idempotent(tmp_path: Path) -> None:
    """If spec 008 has not yet shipped, ``unidentified_dump.library_id``
    does not exist — the migration must skip the FK finalisation
    branch silently rather than failing."""
    db = tmp_path / "test_no_dump_column.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        # unidentified_dump exists (spec 001) but does NOT yet carry
        # library_id (spec 008 hasn't shipped). Confirm the column is
        # absent so the test premise holds, and confirm no FK referring
        # to library was added (since there's no column to reference).
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(unidentified_dump)")
        }
        assert "library_id" not in columns

        # And every existing unidentified_dump FK still points at its
        # original target (no new library FK).
        ud_fks = _foreign_keys(conn, "unidentified_dump")
        assert ("library", "id") not in ud_fks
    finally:
        conn.close()
