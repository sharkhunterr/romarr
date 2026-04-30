"""Migration 0006 end-to-end test (T012-T013)."""

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


def test_creates_six_tables_and_m2m(tmp_path: Path) -> None:
    """Applying the migration creates all six profile tables + m2m
    with the documented constraints."""
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
        for expected in (
            "quality_profile",
            "region_profile",
            "dump_profile",
            "language_profile",
            "naming_profile",
            "custom_format",
            "library_custom_format",
        ):
            assert expected in tables, f"missing table: {expected}"

        # CHECK constraint on dump_profile.prefer_revision fires.
        try:
            cur.execute(
                "INSERT INTO dump_profile "
                "(name, allowed_dump_status, prefer_revision, "
                " is_user_modified, is_factory_default, "
                " allow_proto_beta, allow_hacks, allow_trainers, allow_translations, "
                " created_at, updated_at) VALUES "
                "('bad', '[\"verified\"]', 'bogus', 0, 0, 0, 0, 0, 0, "
                " current_timestamp, current_timestamp)"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on prefer_revision did not fire")

        # CHECK constraint on naming_profile.convention fires.
        try:
            cur.execute(
                "INSERT INTO naming_profile "
                "(name, convention, template, "
                " platform_subfolder, replace_illegal_chars, multi_disc_subfolder, "
                " is_user_modified, is_factory_default, created_at, updated_at) VALUES "
                "('bad', 'not-real', '{}', 1, 1, 1, 0, 0, "
                " current_timestamp, current_timestamp)"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on convention did not fire")

        # CHECK constraint on custom_format.score fires (out of range).
        try:
            cur.execute(
                "INSERT INTO custom_format "
                "(name, score, conditions, is_user_modified, is_factory_default, "
                " created_at, updated_at) VALUES "
                "('bad', 100000, '[]', 0, 0, "
                " current_timestamp, current_timestamp)"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on score did not fire")

        # m2m composite PK exists on (library_id, custom_format_id).
        cf_pk = list(cur.execute("PRAGMA table_info(library_custom_format)"))
        pk_cols = sorted(row[1] for row in cf_pk if row[5] > 0)
        assert pk_cols == ["custom_format_id", "library_id"]
    finally:
        conn.close()


def test_seed_key_partial_unique_index(tmp_path: Path) -> None:
    """seed_key NULL is allowed many times; non-NULL must be unique (FR-003a)."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        # Two rows with NULL seed_key → fine.
        cur.execute(
            "INSERT INTO quality_profile "
            "(name, allowed_formats, preferred_format, upgrade_until_format, "
            " is_user_modified, is_factory_default, "
            " require_dat_verified, allow_archive_double_compression, "
            " created_at, updated_at) VALUES "
            "('A', '[\"raw\"]', 'raw', 'raw', 0, 0, 0, 0, "
            " current_timestamp, current_timestamp)"
        )
        cur.execute(
            "INSERT INTO quality_profile "
            "(name, allowed_formats, preferred_format, upgrade_until_format, "
            " is_user_modified, is_factory_default, "
            " require_dat_verified, allow_archive_double_compression, "
            " created_at, updated_at) VALUES "
            "('B', '[\"raw\"]', 'raw', 'raw', 0, 0, 0, 0, "
            " current_timestamp, current_timestamp)"
        )
        conn.commit()

        # Two rows with the same non-NULL seed_key → blocked.
        cur.execute(
            "UPDATE quality_profile SET seed_key='preservation' WHERE name='A'"
        )
        conn.commit()
        try:
            cur.execute(
                "UPDATE quality_profile SET seed_key='preservation' WHERE name='B'"
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("partial unique index on seed_key did not fire")
    finally:
        conn.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0005_download_clients")
    command.upgrade(cfg, "head")
