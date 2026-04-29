"""Spec 010 migration test — apply 0010_auth_multiuser to a fresh DB."""

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


def test_migration_creates_auth_tables_and_seeds_system_user(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        tables = sorted(
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        )
        # Spec 001 tables + spec 010 tables.
        assert "user" in tables
        assert "session" in tables
        assert "api_key" in tables
        assert "setup_token" in tables

        # System sentinel row exists at id=0.
        rows = cur.execute(
            "SELECT id, username, role, is_active FROM user WHERE id = 0"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "system"
        assert rows[0][2] == "admin"
        assert rows[0][3] == 0  # SQLite stores boolean as 0/1
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
