"""Migration 0007 end-to-end test (T008)."""

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


def test_creates_three_tables_and_indexer_column(tmp_path: Path) -> None:
    """Applying the migration creates all three new tables AND adds
    indexer.rss_auto_grab with DEFAULT true."""
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
        for expected in ("blocklist", "search_history", "search_cache"):
            assert expected in tables, f"missing table: {expected}"

        # New indexer column with DEFAULT true.
        idx_columns = {
            r[1]: r for r in cur.execute("PRAGMA table_info(indexer)").fetchall()
        }
        assert "rss_auto_grab" in idx_columns

        # CHECK constraint on search_type fires.
        try:
            cur.execute(
                "INSERT INTO search_history "
                "(search_type, results_count, started_at, correlation_id) "
                "VALUES ('not-a-real-type', 0, current_timestamp, 'corr-1')"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on search_type did not fire")

        # UNIQUE on (indexer_id, cache_key).
        cur.execute(
            "INSERT INTO indexer (name, implementation, url, categories, "
            " source, created_at, updated_at) VALUES "
            "('idx', 'newznab', 'https://idx.test/api', '[]', 'manual', "
            " current_timestamp, current_timestamp)"
        )
        cur.execute("SELECT last_insert_rowid()")
        idx_id = cur.fetchone()[0]
        for _ in range(2):
            try:
                cur.execute(
                    "INSERT INTO search_cache "
                    "(indexer_id, cache_key, query, category_ids, "
                    " response_xml, parsed_results, fetched_at, "
                    " expires_at, last_read_at, created_at, updated_at) "
                    f"VALUES ({idx_id}, 'k1', 'q', '[1060]', x'00', '[]', "
                    " current_timestamp, current_timestamp, "
                    " current_timestamp, current_timestamp, current_timestamp)"
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # The second insert is the one that should fail.
                break
        else:  # pragma: no cover
            raise AssertionError("UNIQUE (indexer_id, cache_key) did not fire")
    finally:
        conn.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0006_profiles")
    command.upgrade(cfg, "head")
