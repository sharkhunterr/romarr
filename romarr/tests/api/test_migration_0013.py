"""Spec 013 migration smoke tests (T005).

Mirrors the spec-012 pattern: raw ``sqlite3`` for table-name and
column introspection so we don't tangle the test in the project's
async fixtures.
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


def test_migration_creates_four_tables(tmp_path: Path) -> None:
    db = tmp_path / "0013.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    tables = _table_names(db)
    assert "tag" in tables
    assert "tag_assignment" in tables
    assert "queue_entry" in tables
    assert "idempotency_cache" in tables


def test_migration_is_reversible(tmp_path: Path) -> None:
    db = tmp_path / "0013-reversible.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0012_tasks")

    tables = _table_names(db)
    assert "tag" not in tables
    assert "tag_assignment" not in tables
    assert "queue_entry" not in tables
    assert "idempotency_cache" not in tables


def test_migration_creates_documented_columns(tmp_path: Path) -> None:
    """Sanity check that the columns we'll need at runtime exist
    — the Tag UI reads ``color`` and ``label``, the queue
    reconciler reads ``download_client_native_id``, the
    idempotency middleware reads ``request_body_hash``."""
    db = tmp_path / "0013-columns.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        tag_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(tag)")
        }
        assignment_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(tag_assignment)")
        }
        queue_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(queue_entry)")
        }
        cache_cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(idempotency_cache)"
            )
        }
    finally:
        conn.close()

    assert {
        "id",
        "name",
        "color",
        "label",
        "created_at",
        "updated_at",
    }.issubset(tag_cols)

    assert {
        "id",
        "tag_id",
        "entity_type",
        "entity_id",
        "created_at",
    }.issubset(assignment_cols)

    assert {
        "id",
        "release_id",
        "download_client_id",
        "download_client_native_id",
        "state",
        "progress",
        "size_bytes",
        "eta_seconds",
        "last_updated_at",
        "error_msg",
        "attempt_count",
        "last_attempt_at",
        "created_at",
    }.issubset(queue_cols)

    assert {
        "endpoint",
        "key",
        "request_body_hash",
        "response_status",
        "response_body",
        "response_headers",
        "created_at",
        "expires_at",
    }.issubset(cache_cols)


def test_idempotency_cache_uses_composite_pk(tmp_path: Path) -> None:
    """The PK is ``(endpoint, key)`` — same key on a different
    endpoint is a separate cache slot."""
    db = tmp_path / "0013-pk.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        # PRAGMA table_info reports `pk` column = position in PK
        # (1-based), 0 if not part of PK.
        rows = list(
            conn.execute("PRAGMA table_info(idempotency_cache)")
        )
    finally:
        conn.close()

    pk_columns = {row[1] for row in rows if row[5] > 0}
    assert pk_columns == {"endpoint", "key"}


def test_tag_color_default_is_brand_green(tmp_path: Path) -> None:
    """``tag.color`` defaults to the Game Boy LCD green (spec 014)."""
    db = tmp_path / "0013-default.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO tag (name, label) VALUES ('demo', 'Demo')"
        )
        conn.commit()
        row = conn.execute(
            "SELECT color FROM tag WHERE name='demo'"
        ).fetchone()
    finally:
        conn.close()

    assert row[0] == "#9BBC0F"
