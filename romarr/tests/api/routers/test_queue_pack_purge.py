"""``_purge_pack_artifacts`` cleanup test.

The failed-and-acknowledged flow used to leave the pack's
downloaded archive + every ``rom_pack_<id>_*`` extract tempdir on
disk forever — the API just dropped the QueueEntry row and exited.
One install accumulated 29 GB of orphan tempdirs across cancelled
retries before we noticed. This module pins the new behaviour:
purge the archive (url packs only), and rmtree every per-pack
tempdir under the configured download root.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.routers.queue import _purge_pack_artifacts
from romarr.domain.models import RomPack


async def _seed_pack(
    session: AsyncSession,
    *,
    download_dir: Path,
    source_kind: str = "url",
    downloaded_path: Path | None = None,
) -> RomPack:
    """Seed a RomPack row + the matching RomPackConfig pointing at
    the test tempdir."""
    from romarr.domain.models import RomPackConfig

    config = (
        await session.execute(
            __import__("sqlalchemy").select(RomPackConfig).limit(1)
        )
    ).scalar_one_or_none()
    if config is None:
        config = RomPackConfig(download_dir=str(download_dir))
        session.add(config)
    else:
        config.download_dir = str(download_dir)
    pack_kwargs: dict = dict(
        name=f"pack-{uuid4().hex[:6]}",
        source_kind=source_kind,
        downloaded_path=str(downloaded_path) if downloaded_path else None,
        status="failed",
    )
    if source_kind == "url":
        pack_kwargs["url"] = "https://example.test/pack.zip"
    else:
        # grab packs are constrained to (client_id, native_id) non-null.
        pack_kwargs["download_client_id"] = 1
        pack_kwargs["download_client_native_id"] = "fake-hash"
    pack = RomPack(**pack_kwargs)
    session.add(pack)
    await session.commit()
    await session.refresh(pack)
    return pack


@pytest.mark.asyncio
async def test_purge_removes_url_pack_archive(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    archive = tmp_path / "pack.zip"
    archive.write_bytes(b"zip-bytes")
    pack = await _seed_pack(
        async_session,
        download_dir=tmp_path,
        source_kind="url",
        downloaded_path=archive,
    )

    await _purge_pack_artifacts(async_session, pack_id=pack.id)

    assert not archive.exists()


@pytest.mark.asyncio
async def test_purge_removes_every_rom_pack_tempdir(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """``tempfile.mkdtemp(prefix=f"rom_pack_{id}_")`` leaves a
    matching dir per failed attempt; purge them all."""
    pack = await _seed_pack(async_session, download_dir=tmp_path)
    # Three failed attempts → three tempdirs
    leftovers = [
        tmp_path / f"rom_pack_{pack.id}_aaa",
        tmp_path / f"rom_pack_{pack.id}_bbb",
        tmp_path / f"rom_pack_{pack.id}_ccc",
    ]
    for d in leftovers:
        d.mkdir()
        (d / "rom.iso").write_bytes(b"x" * 64)
    # An unrelated tempdir for a DIFFERENT pack id must survive.
    other = tmp_path / "rom_pack_999_unrelated"
    other.mkdir()
    (other / "other.iso").write_bytes(b"y")

    await _purge_pack_artifacts(async_session, pack_id=pack.id)

    for d in leftovers:
        assert not d.exists(), d
    assert other.exists(), "unrelated pack's tempdir must not be touched"


@pytest.mark.asyncio
async def test_purge_skips_grab_pack_archive(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Grab-sourced packs share their archive with the qBit
    torrent; that file's lifecycle belongs to the download
    client, not Romarr — leave it alone."""
    archive = tmp_path / "grabbed.zip"
    archive.write_bytes(b"zip")
    pack = await _seed_pack(
        async_session,
        download_dir=tmp_path,
        source_kind="grab",
        downloaded_path=archive,
    )

    await _purge_pack_artifacts(async_session, pack_id=pack.id)

    assert archive.exists(), "grab-pack archive belongs to qBit"


@pytest.mark.asyncio
async def test_purge_missing_pack_is_noop(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """No pack row → silent return."""
    await _purge_pack_artifacts(async_session, pack_id=999_999)
