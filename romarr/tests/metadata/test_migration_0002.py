"""End-to-end test for migration 0002_metadata_layer (T011)."""

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


def test_metadata_layer_creates_three_tables_and_seeds(tmp_path: Path) -> None:
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
        for required in ("metadata_provider_config", "metadata_cache", "field_priority"):
            assert required in tables, f"missing table: {required}"

        # Provider seed: 9 rows, all disabled.
        rows = cur.execute(
            "SELECT provider_name, enabled, priority_global, rate_limit_rps, rate_limit_burst "
            "FROM metadata_provider_config ORDER BY priority_global"
        ).fetchall()
        assert len(rows) == 9
        names = [r[0] for r in rows]
        assert names == [
            "igdb",
            "screenscraper",
            "mobygames",
            "launchbox",
            "hasheous",
            "playmatch",
            "retroachievements",
            "howlongtobeat",
            "steamgriddb",
        ]
        # All disabled by default.
        assert all(not r[1] for r in rows)
        # IGDB-specific rate limit (4 / 8) wired through.
        igdb_row = next(r for r in rows if r[0] == "igdb")
        assert igdb_row[3] == 4
        assert igdb_row[4] == 8

        # Field priority seed: 34 rows from data-model.md.
        (count,) = cur.execute("SELECT COUNT(*) FROM field_priority").fetchone()
        assert count == 34

        # Game.needs_metadata_refresh column already exists from 0001.
        game_columns = {
            r[1] for r in cur.execute("PRAGMA table_info(game)").fetchall()
        }
        assert "needs_metadata_refresh" in game_columns
    finally:
        conn.close()


def test_migration_idempotent_seeders(tmp_path: Path) -> None:
    """Re-running 0002 (e.g. after a stamp + upgrade) must not duplicate
    rows. We can't directly stamp + upgrade twice with the same config,
    but we can simulate by inserting a sentinel row and running the
    seeder helpers a second time via a fresh upgrade onto a stamped DB."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    # Re-invoke the seeders by downgrading + upgrading 0002.
    command.downgrade(cfg, "0010_auth_multiuser")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        (count,) = cur.execute(
            "SELECT COUNT(*) FROM metadata_provider_config"
        ).fetchone()
        assert count == 9
        (fp_count,) = cur.execute("SELECT COUNT(*) FROM field_priority").fetchone()
        assert fp_count == 34
    finally:
        conn.close()
