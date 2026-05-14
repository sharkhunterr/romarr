"""Unit tests for the ROM content-pack ingest helpers (slice 460).

Covers the self-contained pieces — the streaming download cap,
the free-space pre-check, DAT-match authority resolution and
find-or-create-game — without driving a full
``ingest_rom_pack`` (that needs a live archive + importer and is
better exercised at the integration layer).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.models import QueueEntry
from romarr.domain.models import DatEntry, Game, Platform
from romarr.rom_packs.ingest import (
    RomPackIngestError,
    _find_or_create_game,
    _precheck_free_space,
    _resolve_dat_match,
    _settle_queue_entry,
    _stream_download,
    _update_queue_progress,
    _upsert_queue_entry,
)

# --------------------------------------------------------------------------
# _stream_download
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_download_writes_file(tmp_path: Path) -> None:
    dest = tmp_path / "pack.zip"
    with respx.mock:
        respx.get("https://example.com/p.zip").mock(
            return_value=httpx.Response(200, content=b"x" * 4096)
        )
        written = await _stream_download(
            url="https://example.com/p.zip", dest=dest, max_bytes=10_000
        )
    assert written == 4096
    assert dest.read_bytes() == b"x" * 4096


@pytest.mark.asyncio
async def test_stream_download_enforces_cap(tmp_path: Path) -> None:
    """A body past ``max_bytes`` trips the cap and the partial
    file is cleaned up."""
    dest = tmp_path / "huge.zip"
    with respx.mock:
        respx.get("https://example.com/huge.zip").mock(
            return_value=httpx.Response(200, content=b"y" * (3 * 1024 * 1024))
        )
        with pytest.raises(RomPackIngestError, match="cap"):
            await _stream_download(
                url="https://example.com/huge.zip",
                dest=dest,
                max_bytes=1024 * 1024,
            )
    assert not dest.exists()


@pytest.mark.asyncio
async def test_stream_download_raises_on_upstream_error(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "missing.zip"
    with respx.mock:
        respx.get("https://example.com/404.zip").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(RomPackIngestError, match="404"):
            await _stream_download(
                url="https://example.com/404.zip",
                dest=dest,
                max_bytes=10_000,
            )


# --------------------------------------------------------------------------
# _precheck_free_space
# --------------------------------------------------------------------------


def test_precheck_free_space_passes_on_normal_volume(tmp_path: Path) -> None:
    # tmp_path's volume has far more than the 5 GiB floor in CI;
    # a tiny hint stays well under that.
    _precheck_free_space(tmp_path, archive_size_hint=1024)


def test_precheck_free_space_rejects_huge_hint(tmp_path: Path) -> None:
    # 2x an absurd hint can't fit on any real test volume.
    with pytest.raises(RomPackIngestError, match="insufficient disk space"):
        _precheck_free_space(
            tmp_path, archive_size_hint=10 ** 18
        )


# --------------------------------------------------------------------------
# _resolve_dat_match
# --------------------------------------------------------------------------


async def _seed_platform(session: AsyncSession, slug: str) -> Platform:
    platform = Platform(slug=slug, name=slug.upper())
    session.add(platform)
    await session.flush()
    return platform


@pytest.mark.asyncio
async def test_resolve_dat_match_returns_none_when_no_hash(
    async_session: AsyncSession,
) -> None:
    match = await _resolve_dat_match(
        async_session, sha1="deadbeef" * 5, platform_id=None
    )
    assert match is None


@pytest.mark.asyncio
async def test_resolve_dat_match_prefers_no_intro_authority(
    async_session: AsyncSession,
) -> None:
    platform = await _seed_platform(async_session, "gba")
    sha1 = "a" * 40
    async_session.add_all(
        [
            DatEntry(
                platform_id=platform.id,
                source="tosec",
                name="Game (TOSEC)",
                sha1=sha1,
                dat_contents_hash="h1",
            ),
            DatEntry(
                platform_id=platform.id,
                source="no-intro",
                name="Game (No-Intro)",
                sha1=sha1,
                dat_contents_hash="h2",
            ),
        ]
    )
    await async_session.commit()

    match = await _resolve_dat_match(
        async_session, sha1=sha1.upper(), platform_id=platform.id
    )
    assert match is not None
    assert match.source == "no-intro"


# --------------------------------------------------------------------------
# _find_or_create_game
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_or_create_game_creates_monitored_game(
    async_session: AsyncSession,
) -> None:
    platform = await _seed_platform(async_session, "snes")
    entry = DatEntry(
        platform_id=platform.id,
        source="no-intro",
        name="Super Mario World",
        sha1="b" * 40,
        dat_contents_hash="h",
    )
    async_session.add(entry)
    await async_session.flush()

    game = await _find_or_create_game(async_session, dat_entry=entry)
    assert game.id is not None
    assert game.platform_id == platform.id
    assert game.slug == "super-mario-world"
    assert game.title == "Super Mario World"
    assert game.monitored is True
    assert game.needs_metadata_refresh is True


@pytest.mark.asyncio
async def test_find_or_create_game_reuses_existing(
    async_session: AsyncSession,
) -> None:
    platform = await _seed_platform(async_session, "nes")
    existing = Game(
        platform_id=platform.id,
        slug="metroid",
        title="Metroid",
        monitored=False,
    )
    async_session.add(existing)
    entry = DatEntry(
        platform_id=platform.id,
        source="no-intro",
        name="Metroid",
        sha1="c" * 40,
        dat_contents_hash="h",
    )
    async_session.add(entry)
    await async_session.flush()

    game = await _find_or_create_game(async_session, dat_entry=entry)
    assert game.id == existing.id
    # Existing row is reused as-is — not flipped to monitored.
    assert game.monitored is False


# --------------------------------------------------------------------------
# queue_entry mirror — URL packs in Activity → Queue (slice 465)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_entry_mirror_lifecycle(
    async_sessionmaker_factory: object,
) -> None:
    """A URL pack mirrors its transfer into ``queue_entry`` with a
    NULL ``download_client_id``; progress refreshes it; a
    successful settle deletes it."""
    from sqlalchemy import select

    sm = async_sessionmaker_factory

    await _upsert_queue_entry(sm, rom_pack_id=7, title="No-Intro GBA")
    async with sm() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == "rom_pack:7"
                )
            )
        ).scalar_one()
        # Romarr-internal download — no originating client.
        assert row.download_client_id is None
        assert row.state == "downloading"
        assert row.progress == 0.0

    await _update_queue_progress(
        sm, rom_pack_id=7, written=512, total=1024
    )
    async with sm() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == "rom_pack:7"
                )
            )
        ).scalar_one()
        assert row.progress == 0.5
        assert row.size_bytes == 1024

    await _settle_queue_entry(sm, rom_pack_id=7, success=True)
    async with sm() as session:
        gone = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == "rom_pack:7"
                )
            )
        ).scalar_one_or_none()
        assert gone is None


@pytest.mark.asyncio
async def test_queue_entry_settle_failure_keeps_row(
    async_sessionmaker_factory: object,
) -> None:
    """A failed download flips the mirror to ``failed`` with the
    error so Activity surfaces it — the row is kept, not deleted."""
    from sqlalchemy import select

    sm = async_sessionmaker_factory
    await _upsert_queue_entry(sm, rom_pack_id=9, title="Broken pack")
    await _settle_queue_entry(
        sm, rom_pack_id=9, success=False, error="upstream 404"
    )
    async with sm() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == "rom_pack:9"
                )
            )
        ).scalar_one()
        assert row.state == "failed"
        assert row.error_msg == "upstream 404"
