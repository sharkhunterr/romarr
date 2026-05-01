"""DB-update step tests (T068-T071, FR-027 / FR-028)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.identification.hasher import HashResult
from romarr.importer.steps.db_update import persist_dump

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _seed_release(session: AsyncSession) -> Release:
    platform = Platform(name="Mega Drive", slug="megadrive-dbup")
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    game = Game(platform_id=platform.id, slug="sonic", title="Sonic the Hedgehog")
    session.add(game)
    await session.commit()
    await session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
    )
    session.add(release)
    await session.commit()
    await session.refresh(release)
    return release


def _hashes(*, sha1: str = "a" * 40) -> HashResult:
    return HashResult(
        crc32="aabbccdd",
        md5="d" * 32,
        sha1=sha1,
        sha256=None,
        size_bytes=524288,
    )


# ---------------------------------------------------------------------------
# T068 — creates Dump with all hashes + DAT metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_dump_with_all_hashes(
    async_session: AsyncSession,
) -> None:
    release = await _seed_release(async_session)
    dump = await persist_dump(
        session=async_session,
        release_id=release.id,
        dump_path=Path("/library/megadrive/Sonic.md"),
        original_filename="Sonic the Hedgehog.md",
        hashes=_hashes(sha1="abcdef" + "0" * 34),
        file_format="md",
        dat_verified=True,
        dat_source="no-intro",
        imported_via="manual",
        imported_by="alice",
    )
    await async_session.commit()

    assert dump.id is not None
    assert dump.path == "/library/megadrive/Sonic.md"
    assert dump.crc32 == "aabbccdd"
    assert dump.sha1 == "abcdef" + "0" * 34
    assert dump.format == "md"
    assert dump.dat_verified is True
    assert dump.dat_source == "no-intro"
    assert dump.imported_via == "manual"
    assert dump.imported_by == "alice"
    assert dump.imported_at is not None
    assert dump.size_bytes == 524288


# ---------------------------------------------------------------------------
# T069 — Release.status flips to 'imported'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_status_flips_to_imported(
    async_session: AsyncSession,
) -> None:
    release = await _seed_release(async_session)
    assert release.status == "wanted"

    await persist_dump(
        session=async_session,
        release_id=release.id,
        dump_path=Path("/library/megadrive/Sonic.md"),
        original_filename="Sonic.md",
        hashes=_hashes(),
        file_format="md",
    )
    await async_session.commit()

    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed.status == "imported"
    assert refreshed.cutoff_met is False


# ---------------------------------------------------------------------------
# T070 — keep_dump_history=False deletes prior Dumps for the Release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_dump_history_false_replaces_old_dump(
    async_session: AsyncSession,
) -> None:
    release = await _seed_release(async_session)

    # Pre-existing Dump that should be retired.
    old = Dump(
        release_id=release.id,
        path="/library/megadrive/old.md",
        original_filename="old.md",
        size_bytes=100,
        format="md",
        crc32="00000000",
        md5="0" * 32,
        sha1="0" * 40,
    )
    async_session.add(old)
    await async_session.commit()
    old_id = old.id

    new_dump = await persist_dump(
        session=async_session,
        release_id=release.id,
        dump_path=Path("/library/megadrive/new.md"),
        original_filename="new.md",
        hashes=_hashes(sha1="b" * 40),
        file_format="md",
        keep_dump_history=False,
    )
    await async_session.commit()

    del old_id  # SQLite may recycle rowids; we assert by content below.

    # Old Dump is gone; new Dump survives. The retired old row's
    # path/sha1 don't show up in the table anymore.
    rows = (
        (await async_session.execute(
            select(Dump).where(Dump.release_id == release.id)
        )).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].id == new_dump.id
    assert rows[0].sha1 == "b" * 40
    assert rows[0].path == "/library/megadrive/new.md"


# ---------------------------------------------------------------------------
# T071 — keep_dump_history=True appends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_dump_history_true_appends(
    async_session: AsyncSession,
) -> None:
    release = await _seed_release(async_session)

    old = Dump(
        release_id=release.id,
        path="/library/megadrive/old.md",
        original_filename="old.md",
        size_bytes=100,
        format="md",
        crc32="00000000",
        md5="0" * 32,
        sha1="0" * 40,
    )
    async_session.add(old)
    await async_session.commit()
    old_id = old.id

    new_dump = await persist_dump(
        session=async_session,
        release_id=release.id,
        dump_path=Path("/library/megadrive/new.md"),
        original_filename="new.md",
        hashes=_hashes(sha1="b" * 40),
        file_format="md",
        keep_dump_history=True,
    )
    await async_session.commit()

    rows = (
        (await async_session.execute(
            select(Dump).where(Dump.release_id == release.id)
        )).scalars().all()
    )
    assert {r.id for r in rows} == {old_id, new_dump.id}
