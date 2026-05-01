"""Spec 011 migration test — apply 0011_notifications to a fresh DB."""

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


def test_migration_creates_both_tables(tmp_path: Path) -> None:
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
        assert "notification" in tables
        assert "health_check" in tables

        # Notification has the documented columns + UNIQUE name.
        notif_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(notification)")
        }
        assert {
            "name",
            "apprise_url_encrypted",
            "apprise_url_scheme",
            "on_grab",
            "on_import",
            "on_health_issue",
            "tags",
            "enabled",
            "last_status",
        } <= notif_cols

        # HealthCheck carries the persisted debouncer columns.
        hc_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(health_check)")
        }
        assert {
            "component",
            "status",
            "severity_changed_at",
            "last_emitted_state",
            "last_emitted_at",
        } <= hc_cols
    finally:
        conn.close()


def test_migration_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "reversible.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008_import_pipeline")

    conn = sqlite3.connect(db)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
            )
        }
        assert "notification" not in tables
        assert "health_check" not in tables
    finally:
        conn.close()
