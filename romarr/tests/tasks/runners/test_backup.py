"""Tests for the BackupRunner (spec 012 T049 + T044/T045)."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from romarr.config.settings import Settings
from romarr.domain import Base
from romarr.domain.models import Game, Platform
from romarr.tasks.runners.backup import (
    DEFAULT_RETENTION,
    _prune_older,
    run_backup,
)


@pytest.fixture
def settings_for_backup() -> Settings:
    return Settings(
        auth_secret_key="x" * 32,
        oidc_client_secret="hunter2",
        importer_webhook_token="webhook-secret",
    )


@pytest.fixture
async def file_db(tmp_path: Path):
    """A real on-disk SQLite DB so VACUUM INTO has something to
    snapshot. (In-memory DBs can't be VACUUM'd into another
    file.)"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'live.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed a row so the snapshot has something to verify.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug="md", name="MD")
        session.add(platform)
        await session.flush()
        session.add(
            Game(
                platform_id=platform.id,
                slug="sonic",
                title="Sonic",
            )
        )
        await session.commit()

    async with sm() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_backup_writes_db_and_config_tarball(
    file_db: AsyncSession,
    settings_for_backup: Settings,
    tmp_path: Path,
) -> None:
    """spec 012 T044 (test_writes_db_and_config_tar) — both
    files land in ``backup_dir`` and the snapshot contains the
    seeded row."""
    backup_dir = tmp_path / "backups"

    result = await run_backup(
        file_db, backup_dir=backup_dir, settings=settings_for_backup
    )

    assert result.db_path.is_file()
    assert result.config_path.is_file()
    assert result.pruned == []

    # The snapshot is a real SQLite file with the seeded row.
    import sqlite3

    snap = sqlite3.connect(result.db_path)
    try:
        cursor = snap.execute("SELECT title FROM game")
        rows = cursor.fetchall()
    finally:
        snap.close()
    assert rows == [("Sonic",)]

    # Config tarball contains a sanitised settings.json.
    with tarfile.open(result.config_path, "r:gz") as tf:
        names = tf.getnames()
        assert names == ["settings.json"]
        member = tf.extractfile("settings.json")
        assert member is not None
        payload = json.loads(member.read().decode("utf-8"))
    assert payload["auth_secret_key"] == "<redacted>"
    assert payload["oidc_client_secret"] == "<redacted>"
    assert payload["importer_webhook_token"] == "<redacted>"


@pytest.mark.asyncio
async def test_run_backup_keeps_last_30(
    file_db: AsyncSession,
    settings_for_backup: Settings,
    tmp_path: Path,
) -> None:
    """spec 012 T045 (test_keeps_last_30) — once the directory
    holds more than ``DEFAULT_RETENTION`` archives, the older
    ones get pruned. We seed 32 fake archives + run one real
    backup and assert exactly 30 sqlite files remain."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Seed 32 dummy archive pairs with predictable mtimes.
    import time

    base = time.time() - 10_000
    for i in range(32):
        sqlite = backup_dir / f"romarr-fake{i:03d}.sqlite"
        config = backup_dir / f"romarr-fake{i:03d}-config.tar.gz"
        sqlite.write_bytes(b"fake")
        config.write_bytes(b"fake-config")
        # Stagger mtimes so the prune sees a clear ordering.
        ts = base + i
        for path in (sqlite, config):
            import os

            os.utime(path, (ts, ts))

    # The real backup adds one more (the newest), then prunes.
    result = await run_backup(
        file_db,
        backup_dir=backup_dir,
        settings=settings_for_backup,
    )

    sqlite_files = list(backup_dir.glob("romarr-*.sqlite"))
    assert len(sqlite_files) == DEFAULT_RETENTION
    # The just-written backup is the newest and survives.
    assert result.db_path.is_file()


def test_prune_older_pairs_sqlite_with_config_tarball(
    tmp_path: Path,
) -> None:
    """``_prune_older`` removes the matching config tar.gz when
    it deletes a sqlite snapshot."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    import time

    base = time.time() - 1000
    for i in range(5):
        sqlite = backup_dir / f"romarr-{i}.sqlite"
        config = backup_dir / f"romarr-{i}-config.tar.gz"
        sqlite.write_bytes(b"x")
        config.write_bytes(b"y")
        import os

        os.utime(sqlite, (base + i, base + i))
        os.utime(config, (base + i, base + i))

    pruned = _prune_older(backup_dir, retention=2)
    # 5 - 2 = 3 sqlite + 3 configs pruned.
    sqlite_pruned = [p for p in pruned if p.suffix == ".sqlite"]
    config_pruned = [p for p in pruned if p.name.endswith("-config.tar.gz")]
    assert len(sqlite_pruned) == 3
    assert len(config_pruned) == 3

    # The two newest pairs survive.
    surviving = sorted(backup_dir.glob("romarr-*.sqlite"))
    assert len(surviving) == 2
    assert "romarr-3.sqlite" in {p.name for p in surviving}
    assert "romarr-4.sqlite" in {p.name for p in surviving}
