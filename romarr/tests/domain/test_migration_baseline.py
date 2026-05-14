"""End-to-end migration test — apply 0001 and verify FR-009 seed.

Spec 001 SC-008: foundation modules MUST be importable and verifiable
without booting the HTTP layer. This test exercises the migration
itself against an isolated SQLite file.
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


def test_migration_creates_nine_tables_and_seeds_five_platforms(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")

    command.upgrade(cfg, "head")

    # Use the synchronous sqlite3 driver to inspect — avoids spinning
    # an event loop just for DDL introspection.
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
        # Spec 001's nine foundation tables MUST all exist; later
        # specs (e.g., 010-auth-multiuser) add their own tables on top
        # so we assert containment rather than equality.
        foundation_tables = {
            "dat_entry",
            "dump",
            "game",
            "platform",
            "platform_format",
            "platform_naming_token",
            "platform_pack",
            "release",
            "unidentified_dump",
        }
        assert foundation_tables.issubset(tables)

        platforms = cur.execute(
            "SELECT slug FROM platform ORDER BY id"
        ).fetchall()
        # Slice 401 — alembic 0019 renames ``megadrive`` to the
        # RomM-canonical ``genesis`` for folder-name alignment.
        # Slice 455 — alembic 0028 likewise renames ``gameboy`` to
        # ``gb`` (matching the gbc / gba siblings + RomM).
        assert [r[0] for r in platforms] == [
            "nes",
            "snes",
            "genesis",
            "gb",
            "gba",
        ]

        format_count = cur.execute("SELECT COUNT(*) FROM platform_format").fetchone()[0]
        assert format_count >= 5  # at least one format per platform

        pack_rows = cur.execute(
            "SELECT pack_version, schema_version, pack_source FROM platform_pack"
        ).fetchall()
        assert pack_rows == [("2026.04.001", 1, "builtin")]
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
