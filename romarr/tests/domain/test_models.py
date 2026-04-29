"""ORM round-trip tests for the foundation models — FR-001 / FR-002 / FR-003 / FR-004 / FR-005."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain import (
    DatEntry,
    Dump,
    DumpStatus,
    Game,
    NamingConvention,
    Platform,
    PlatformFormat,
    Release,
)


async def _make_platform(session: AsyncSession, slug: str = "megadrive") -> Platform:
    p = Platform(slug=slug, name=slug.upper())
    session.add(p)
    await session.flush()
    return p


# ---------------------------------------------------------------------------
# FR-002 — Game bound to exactly one Platform
# ---------------------------------------------------------------------------


async def test_game_persists_with_unique_slug_per_platform(
    async_session: AsyncSession,
) -> None:
    p = await _make_platform(async_session)
    g = Game(platform_id=p.id, slug="sonic-the-hedgehog", title="Sonic the Hedgehog")
    async_session.add(g)
    await async_session.flush()

    # Same slug on the same platform → integrity error
    dup = Game(platform_id=p.id, slug="sonic-the-hedgehog", title="Sonic Bis")
    async_session.add(dup)
    with pytest.raises(IntegrityError):
        await async_session.flush()
    await async_session.rollback()


async def test_same_title_two_platforms_two_games(async_session: AsyncSession) -> None:
    """Sonic on Mega Drive and Sonic on GBA are TWO distinct Games."""
    md = await _make_platform(async_session, slug="megadrive")
    gba = await _make_platform(async_session, slug="gba")
    async_session.add_all(
        [
            Game(platform_id=md.id, slug="sonic", title="Sonic the Hedgehog"),
            Game(platform_id=gba.id, slug="sonic", title="Sonic the Hedgehog"),
        ]
    )
    await async_session.flush()

    rows = (
        await async_session.execute(select(Game).order_by(Game.platform_id))
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].platform_id != rows[1].platform_id


# ---------------------------------------------------------------------------
# FR-004 — multi-disc parent invariant
# ---------------------------------------------------------------------------


async def test_multidisc_parent_link_succeeds(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session, slug="psx")
    g = Game(platform_id=p.id, slug="ff9", title="Final Fantasy IX")
    async_session.add(g)
    await async_session.flush()

    parent = Release(
        game_id=g.id,
        name="FFIX (USA) (Disc 1)",
        disc_number=1,
        disc_total=2,
    )
    async_session.add(parent)
    await async_session.flush()

    child = Release(
        game_id=g.id,
        name="FFIX (USA) (Disc 2)",
        disc_number=2,
        disc_total=2,
        parent_release_id=parent.id,
    )
    async_session.add(child)
    await async_session.flush()

    assert child.parent_release_id == parent.id


async def test_multidisc_child_without_parent_rejected(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session, slug="psx")
    g = Game(platform_id=p.id, slug="ff9", title="Final Fantasy IX")
    async_session.add(g)
    await async_session.flush()

    bad = Release(
        game_id=g.id,
        name="FFIX (USA) (Disc 2)",
        disc_number=2,
        disc_total=2,
        parent_release_id=None,
    )
    async_session.add(bad)
    with pytest.raises(IntegrityError):
        await async_session.flush()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# FR-005 — Dump path globally unique; cascade on Release delete
# ---------------------------------------------------------------------------


async def test_dump_path_globally_unique(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session)
    g = Game(platform_id=p.id, slug="sonic", title="Sonic")
    async_session.add(g)
    await async_session.flush()
    r = Release(game_id=g.id, name="Sonic (USA)")
    async_session.add(r)
    await async_session.flush()

    d1 = Dump(
        release_id=r.id,
        path="/lib/sonic.md",
        original_filename="sonic.md",
        size_bytes=524288,
        format=".md",
        crc32="deadbeef",
        md5="0" * 32,
        sha1="0" * 40,
    )
    async_session.add(d1)
    await async_session.flush()

    d2 = Dump(
        release_id=r.id,
        path="/lib/sonic.md",  # same path
        original_filename="sonic.md",
        size_bytes=524288,
        format=".md",
        crc32="deadbeef",
        md5="0" * 32,
        sha1="0" * 40,
    )
    async_session.add(d2)
    with pytest.raises(IntegrityError):
        await async_session.flush()


# ---------------------------------------------------------------------------
# FR-006 — DAT entry must carry at least one hash
# ---------------------------------------------------------------------------


async def test_dat_entry_requires_at_least_one_hash(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session)
    bad = DatEntry(
        platform_id=p.id,
        source="no-intro",
        name="Sonic (USA)",
        crc32=None,
        md5=None,
        sha1=None,
        status=DumpStatus.VERIFIED,
        dat_contents_hash="0" * 64,
    )
    async_session.add(bad)
    with pytest.raises(IntegrityError):
        await async_session.flush()


# ---------------------------------------------------------------------------
# FR-009 — five MVP platforms + their formats are reachable through ORM
# ---------------------------------------------------------------------------


async def test_platform_format_unique_extension(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session)
    async_session.add(
        PlatformFormat(platform_id=p.id, extension=".md", format_type="cartridge")
    )
    await async_session.flush()
    async_session.add(
        PlatformFormat(platform_id=p.id, extension=".md", format_type="cartridge")
    )
    with pytest.raises(IntegrityError):
        await async_session.flush()


# ---------------------------------------------------------------------------
# Cascades
# ---------------------------------------------------------------------------


async def test_game_delete_cascades_releases_and_dumps(async_session: AsyncSession) -> None:
    p = await _make_platform(async_session)
    g = Game(platform_id=p.id, slug="sonic", title="Sonic")
    async_session.add(g)
    await async_session.flush()
    r = Release(
        game_id=g.id, name="Sonic (USA)", naming_convention=NamingConvention.NO_INTRO
    )
    async_session.add(r)
    await async_session.flush()
    d = Dump(
        release_id=r.id,
        path="/lib/sonic-cascade.md",
        original_filename="sonic.md",
        size_bytes=524288,
        format=".md",
        crc32="deadbeef",
        md5="0" * 32,
        sha1="0" * 40,
    )
    async_session.add(d)
    await async_session.flush()

    await async_session.delete(g)
    await async_session.flush()

    remaining_releases = (await async_session.execute(select(Release))).scalars().all()
    remaining_dumps = (await async_session.execute(select(Dump))).scalars().all()
    assert remaining_releases == []
    assert remaining_dumps == []
