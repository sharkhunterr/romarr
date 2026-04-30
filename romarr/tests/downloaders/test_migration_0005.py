"""Migration 0005 end-to-end test (T012-T013)."""

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


def test_creates_table_and_fk(tmp_path: Path) -> None:
    """Applying the migration creates ``download_client`` AND attaches
    the FK from ``indexer.download_client_id`` (deferred from spec 004)."""
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
        assert "download_client" in tables

        # The deferred FK is now in place.
        fks = list(cur.execute("PRAGMA foreign_key_list(indexer)"))
        download_client_fk = next(
            (fk for fk in fks if fk[3] == "download_client_id"), None
        )
        assert download_client_fk is not None, (
            "indexer.download_client_id FK not installed by 0005"
        )
        # ON DELETE SET NULL — column 6 of PRAGMA foreign_key_list.
        assert download_client_fk[6] == "SET NULL"

        # type CHECK constraint fires on bad input.
        try:
            cur.execute(
                "INSERT INTO download_client "
                "(name, type, host, port, category_default, "
                " ssl_cert_validation, created_at, updated_at) VALUES "
                "('bad', 'not-real', 'x', 8080, 'romarr', 'enabled', "
                " current_timestamp, current_timestamp)"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("CHECK on type did not fire")
    finally:
        conn.close()


def test_indexer_set_null_on_delete(tmp_path: Path) -> None:
    """Deleting a pinned download_client falls indexer.download_client_id
    back to NULL (FR-014 fallback path)."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO download_client "
            "(name, type, host, port, category_default, ssl_cert_validation, "
            " enable_for_torrents, enable_for_usenet, enabled, "
            " remove_completed_downloads, remove_failed_downloads, "
            " priority, use_ssl, created_at, updated_at) VALUES "
            "('qbit', 'qbittorrent', 'qbit.local', 8080, 'romarr', 'enabled', "
            " 1, 0, 1, 0, 1, 1, 0, current_timestamp, current_timestamp)"
        )
        client_id = cur.lastrowid
        cur.execute(
            "INSERT INTO indexer "
            "(name, implementation, url, categories, source, "
            " download_client_id, created_at, updated_at) VALUES "
            "('idx', 'newznab', 'https://idx.test/api', '[]', 'manual', "
            f" {client_id}, current_timestamp, current_timestamp)"
        )
        conn.commit()

        cur.execute(f"DELETE FROM download_client WHERE id = {client_id}")
        conn.commit()

        rows = cur.execute(
            "SELECT download_client_id FROM indexer WHERE name = 'idx'"
        ).fetchall()
        assert rows == [(None,)]
    finally:
        conn.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004_indexers")
    command.upgrade(cfg, "head")
