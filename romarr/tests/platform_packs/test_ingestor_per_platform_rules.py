"""Per-platform ingestion rules (T024, T025, T026)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from romarr.domain.models import Platform, PlatformFormat, PlatformNamingToken
from romarr.platform_packs import IngestSource, ingest_pack


def _community_source() -> IngestSource:
    return IngestSource(pack_source="community", applied_by="alice")


@pytest.mark.asyncio
async def test_insert_new_platform_with_pack_source(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    body = pack_yaml("valid/minimal.yaml")
    result = await ingest_pack(
        async_session,
        sessionmaker=async_sessionmaker_factory,
        content=body,
        source=_community_source(),
    )
    assert result.action == "applied"

    # Re-read in a fresh session.
    sm = async_sessionmaker_factory
    async with sm() as session:
        row = (
            await session.execute(
                select(Platform).where(Platform.slug == "megadrive")
            )
        ).scalar_one()
        assert row.name == "Sega Mega Drive"
        assert row.pack_source == "community"
        assert row.pack_version == "2026.04.001"
        assert row.igdb_id == 29

        formats = (
            (
                await session.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == row.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {f.extension for f in formats} == {".md"}
        assert all(f.pack_source == "community" for f in formats)


@pytest.mark.asyncio
async def test_update_existing_non_user_platform_replaces_formats(
    async_session: AsyncSession,
    async_engine: AsyncEngine,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """A subsequent pack apply on a non-user platform replaces the
    full format set (FR-013)."""
    # Apply a first pack with .md only.
    sm = async_sessionmaker_factory
    async with sm() as s:
        await ingest_pack(
            s,
            sessionmaker=sm,
            content=pack_yaml("valid/minimal.yaml"),
            source=IngestSource(pack_source="builtin", applied_by="system"),
        )

    # Manually push an extra format that the second pack will REPLACE.
    async with sm() as s:
        plat = (
            await s.execute(
                select(Platform).where(Platform.slug == "megadrive")
            )
        ).scalar_one()
        s.add(
            PlatformFormat(
                platform_id=plat.id,
                extension=".bin",
                format_type="cartridge",
                pack_source="builtin",
            )
        )
        await s.commit()

    # Apply a *newer* pack version that defines a different format set.
    new_body = (
        b"pack_version: '2026.05.001'\n"
        b"schema_version: 1\n"
        b"platforms:\n"
        b"  - slug: megadrive\n    name: Sega Mega Drive\n"
        b"    manufacturer: Sega\n"
        b"    formats:\n"
        b"      - extension: '.gen'\n        format_type: cartridge\n"
        b"      - extension: '.md'\n        format_type: cartridge\n"
    )
    async with sm() as s:
        await ingest_pack(
            s,
            sessionmaker=sm,
            content=new_body,
            source=IngestSource(pack_source="community", applied_by="alice"),
        )

    async with sm() as s:
        plat = (
            await s.execute(
                select(Platform).where(Platform.slug == "megadrive")
            )
        ).scalar_one()
        formats = (
            (
                await s.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == plat.id
                    )
                )
            )
            .scalars()
            .all()
        )
    # The previously-injected .bin is GONE; .md + .gen are now the set.
    assert {f.extension for f in formats} == {".md", ".gen"}
    assert plat.pack_source == "community"
    assert plat.pack_version == "2026.05.001"


@pytest.mark.asyncio
async def test_user_overridden_platform_is_skipped(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """A platform with pack_source='user' is preserved verbatim (FR-012,
    SC-003). Pack apply leaves the row + its formats + its tokens
    untouched."""
    sm = async_sessionmaker_factory
    async with sm() as s:
        s.add(
            Platform(
                slug="megadrive",
                name="Operator's Mega Drive",
                manufacturer="Sega",
                pack_source="user",
                pack_version=None,
                igdb_id=999,
            )
        )
        await s.flush()
        plat_id = (
            await s.execute(select(Platform).where(Platform.slug == "megadrive"))
        ).scalar_one().id
        s.add(
            PlatformFormat(
                platform_id=plat_id,
                extension=".user-ext",
                format_type="cartridge",
                pack_source="user",
            )
        )
        await s.commit()

    async with sm() as s:
        result = await ingest_pack(
            s,
            sessionmaker=sm,
            content=pack_yaml("valid/minimal.yaml"),
            source=_community_source(),
        )

    skipped = next(d for d in result.diff if d.slug == "megadrive")
    assert skipped.action == "skipped"
    assert skipped.reason == "user-overridden"

    # The user platform survives — name, igdb_id, and the user format
    # are all unchanged.
    async with sm() as s:
        plat = (
            await s.execute(
                select(Platform).where(Platform.slug == "megadrive")
            )
        ).scalar_one()
        assert plat.name == "Operator's Mega Drive"
        assert plat.pack_source == "user"
        assert plat.igdb_id == 999

        formats = (
            (
                await s.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == plat.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert {f.extension for f in formats} == {".user-ext"}


@pytest.mark.asyncio
async def test_parent_platform_link_resolves(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """``two_platforms.yaml`` ships SNES with parent_platform_slug=nes;
    the FK is set after both platforms land."""
    sm = async_sessionmaker_factory
    async with sm() as s:
        await ingest_pack(
            s,
            sessionmaker=sm,
            content=pack_yaml("valid/two_platforms.yaml"),
            source=_community_source(),
        )

    async with sm() as s:
        snes = (
            await s.execute(select(Platform).where(Platform.slug == "snes"))
        ).scalar_one()
        nes = (
            await s.execute(select(Platform).where(Platform.slug == "nes"))
        ).scalar_one()
        assert snes.parent_platform_id == nes.id

        # Naming token round-tripped from the YAML's `(USA)` pattern.
        tokens = (
            (
                await s.execute(
                    select(PlatformNamingToken).where(
                        PlatformNamingToken.platform_id == nes.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(tokens) == 1
    assert tokens[0].pattern == "\\(USA\\)"
    assert tokens[0].pack_source == "community"
