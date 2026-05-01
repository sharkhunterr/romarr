"""Spec 012 migration smoke tests (T009).

Ensures ``alembic upgrade head`` creates the three documented
tables (``job``, ``job_run``, ``apscheduler_jobs``) and that
``downgrade`` rolls them back cleanly. The tests are sync —
the migration test suite uses raw ``sqlite3`` rather than
SQLAlchemy async to avoid the event-loop nesting that
``alembic.command`` would otherwise trigger.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "src/romarr/db/alembic")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND name <> 'alembic_version'"
            )
        }
    finally:
        conn.close()


def test_migration_creates_three_tables(tmp_path: Path) -> None:
    db = tmp_path / "0012.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    tables = _table_names(db)
    assert "job" in tables
    assert "job_run" in tables
    assert "apscheduler_jobs" in tables


def test_migration_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "0012-reversible.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0011_notifications")

    tables = _table_names(db)
    assert "job" not in tables
    assert "job_run" not in tables
    assert "apscheduler_jobs" not in tables


def test_migration_creates_documented_columns(tmp_path: Path) -> None:
    """Sanity check on the columns we'll need at runtime — the
    seeder writes ``is_factory_default`` and the lifecycle
    helper writes ``cancellation_forced`` so they need to
    exist."""
    db = tmp_path / "0012-columns.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        job_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(job)")
        }
        run_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(job_run)")
        }
    finally:
        conn.close()

    assert {
        "id",
        "name",
        "type",
        "schedule_cron",
        "schedule_interval_seconds",
        "enabled",
        "next_run_at",
        "last_run_at",
        "last_run_duration_ms",
        "last_run_status",
        "last_error",
        "max_concurrent_instances",
        "max_retries",
        "is_factory_default",
        "created_at",
        "updated_at",
    }.issubset(job_cols)

    assert {
        "id",
        "job_id",
        "started_at",
        "finished_at",
        "duration_ms",
        "status",
        "items_processed",
        "error_message",
        "output_summary",
        "triggered_by",
        "triggered_by_user_id",
        "cancellation_forced",
    }.issubset(run_cols)
