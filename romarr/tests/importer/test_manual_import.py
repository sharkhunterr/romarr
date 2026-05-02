"""Tests for the manual-import helper (slice 83)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Dump, Game, Platform, Release
from romarr.identification.hasher import HashResult
from romarr.importer._manual import manual_import_known
from romarr.importer.models import ImportHistory
from romarr.importer.types import ImportContext


async def _seed_release(
    session: AsyncSession, *, suffix: str = ""
) -> tuple[int, int]:
    """Seed Platform + Game + Release. Returns (game_id, release_id)."""
    platform = Platform(slug=f"md-{uuid4().hex[:6]}", name="Mega Drive")
    session.add(platform)
    await session.flush()
    game = Game(
        platform_id=platform.id,
        slug=f"sonic-{uuid4().hex[:6]}",
        title=f"Sonic the Hedgehog{suffix}",
    )
    session.add(game)
    await session.flush()
    release = Release(
        game_id=game.id,
        name=f"Sonic the Hedgehog (USA){suffix}",
    )
    session.add(release)
    await session.flush()
    return game.id, release.id


def _ctx(tmp_path: Path) -> ImportContext:
    src = tmp_path / "downloads" / "rom.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x" * 32)
    return ImportContext(
        source_path=src,
        correlation_id=uuid4(),
        imported_via="manual",
        imported_by="alice",
    )


def _hashes(sha1: str = "a" * 40) -> HashResult:
    return HashResult(
        crc32="d3578bf6",
        md5="d" * 32,
        sha1=sha1,
        sha256=None,
        size_bytes=524288,
    )


@pytest.mark.asyncio
async def test_manual_import_inserts_dump_and_records_success(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    ctx = _ctx(tmp_path)
    game_id, release_id = await _seed_release(async_session)
    dest = tmp_path / "library" / "megadrive" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"y" * 64)

    outcome = await manual_import_known(
        session=async_session,
        context=ctx,
        release_id=release_id,
        game_id=game_id,
        dest_path=dest,
        file_format="md",
        original_filename="Sonic the Hedgehog (USA).md",
        hashes=_hashes(),
        dat_verified=True,
        dat_source="no-intro",
    )
    await async_session.commit()

    assert outcome.success is True
    assert outcome.coalesced is False
    assert outcome.game_id == game_id
    assert outcome.release_id == release_id
    assert outcome.dump_id is not None

    # Dump persisted with the right fields.
    dump = (
        await async_session.execute(
            select(Dump).where(Dump.id == outcome.dump_id)
        )
    ).scalar_one()
    assert dump.path == str(dest)
    assert dump.format == "md"
    assert dump.dat_verified is True
    assert dump.dat_source == "no-intro"
    assert dump.sha1 == "a" * 40

    # Release transitioned to imported.
    rel = (
        await async_session.execute(
            select(Release).where(Release.id == release_id)
        )
    ).scalar_one()
    assert rel.status == "imported"

    # History row recorded.
    history = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == outcome.history_id)
        )
    ).scalar_one()
    assert history.success is True
    assert history.coalesced is False
    assert history.dest_path == str(dest)
    assert history.game_id == game_id
    assert history.release_id == release_id
    assert history.dump_id == outcome.dump_id
    assert history.imported_by == "alice"


@pytest.mark.asyncio
async def test_manual_import_coalesces_when_dump_already_exists(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    ctx = _ctx(tmp_path)
    game_id, release_id = await _seed_release(async_session)
    sha1 = "b" * 40

    # Pre-seed a Dump for the same release_id + sha1.
    pre_existing_dump = Dump(
        release_id=release_id,
        path="/library/megadrive/Sonic_old.md",
        original_filename="Sonic the Hedgehog (USA).md",
        size_bytes=1024,
        format="md",
        crc32="aaaaaaaa",
        md5="0" * 32,
        sha1=sha1,
    )
    async_session.add(pre_existing_dump)
    await async_session.commit()

    dest = tmp_path / "library" / "megadrive" / "Sonic_new.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"y" * 64)

    outcome = await manual_import_known(
        session=async_session,
        context=ctx,
        release_id=release_id,
        game_id=game_id,
        dest_path=dest,
        file_format="md",
        original_filename="Sonic the Hedgehog (USA).md",
        hashes=_hashes(sha1=sha1),
    )
    await async_session.commit()

    assert outcome.success is True
    assert outcome.coalesced is True
    assert outcome.dump_id == pre_existing_dump.id  # Same dump
    assert outcome.dest_path is not None
    assert str(outcome.dest_path) == "/library/megadrive/Sonic_old.md"  # original location

    # Audit row records the coalesced re-attempt.
    history = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == outcome.history_id)
        )
    ).scalar_one()
    assert history.success is True
    assert history.coalesced is True


@pytest.mark.asyncio
async def test_manual_import_hashes_when_caller_omits_them(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """No `hashes` arg → the helper streams the file via the
    foundation's Hasher in a worker thread."""
    ctx = _ctx(tmp_path)
    game_id, release_id = await _seed_release(async_session)
    dest = tmp_path / "library" / "megadrive" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = b"x" * 1024
    dest.write_bytes(payload)

    outcome = await manual_import_known(
        session=async_session,
        context=ctx,
        release_id=release_id,
        game_id=game_id,
        dest_path=dest,
        file_format="md",
        original_filename="Sonic the Hedgehog (USA).md",
    )
    await async_session.commit()

    assert outcome.success is True
    assert outcome.coalesced is False
    dump = (
        await async_session.execute(
            select(Dump).where(Dump.id == outcome.dump_id)
        )
    ).scalar_one()
    assert dump.size_bytes == len(payload)
    # SHA-1 of 1024 'x' bytes is deterministic.
    import hashlib
    expected_sha1 = hashlib.sha1(payload).hexdigest()
    assert dump.sha1 == expected_sha1


@pytest.mark.asyncio
async def test_manual_import_unknown_imported_via_falls_back_to_manual(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """ImportContext is a Pydantic model so its `imported_via`
    is constrained to the literal — but the persist_dump call
    still goes through `_coerce_imported_via` defensively.
    Verify the happy-path values pass through unchanged."""
    ctx = _ctx(tmp_path)
    game_id, release_id = await _seed_release(async_session)
    dest = tmp_path / "library" / "megadrive" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * 64)

    outcome = await manual_import_known(
        session=async_session,
        context=ctx,
        release_id=release_id,
        game_id=game_id,
        dest_path=dest,
        file_format="md",
        original_filename="Sonic.md",
        hashes=_hashes(sha1="c" * 40),
    )
    await async_session.commit()

    dump = (
        await async_session.execute(
            select(Dump).where(Dump.id == outcome.dump_id)
        )
    ).scalar_one()
    assert dump.imported_via == "manual"
