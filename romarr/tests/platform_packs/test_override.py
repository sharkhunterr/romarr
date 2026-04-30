"""User-override + format-mutation tests (T039-T042)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import (
    Platform,
    PlatformFormat,
    PlatformNamingToken,
)
from romarr.platform_packs import (
    IngestSource,
    OverrideRequiredError,
    add_format,
    delete_format,
    ingest_pack,
    mark_overridden,
    release_override,
    update_format,
)


def _community() -> IngestSource:
    return IngestSource(pack_source="community", applied_by="alice")


async def _seed_minimal_pack(
    sm: async_sessionmaker[AsyncSession], pack_yaml: Callable[[str], bytes]
) -> int:
    """Apply ``valid/two_platforms.yaml`` and return the NES platform id."""
    async with sm() as s:
        await ingest_pack(
            s,
            sessionmaker=sm,
            content=pack_yaml("valid/two_platforms.yaml"),
            source=_community(),
        )
    async with sm() as s:
        nes = (
            await s.execute(select(Platform).where(Platform.slug == "nes"))
        ).scalar_one()
        return nes.id


# ---------------------------------------------------------------------------
# T039 — mark_overridden cascades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_overridden_cascades_to_formats_and_tokens(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        await mark_overridden(s, platform_id=nes_id)

    async with sm() as s:
        plat = (
            await s.execute(select(Platform).where(Platform.id == nes_id))
        ).scalar_one()
        formats = (
            (
                await s.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == nes_id
                    )
                )
            )
            .scalars()
            .all()
        )
        tokens = (
            (
                await s.execute(
                    select(PlatformNamingToken).where(
                        PlatformNamingToken.platform_id == nes_id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert plat.pack_source == "user"
    assert all(f.pack_source == "user" for f in formats)
    assert all(t.pack_source == "user" for t in tokens)


@pytest.mark.asyncio
async def test_mark_overridden_idempotent(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)
    async with sm() as s:
        await mark_overridden(s, platform_id=nes_id)
    async with sm() as s:
        # Second call returns the same row, no exception.
        plat = await mark_overridden(s, platform_id=nes_id)
    assert plat.pack_source == "user"


# ---------------------------------------------------------------------------
# T040 — release_override reverts cleanly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_override_resets_pack_source_from_pack_row(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        await mark_overridden(s, platform_id=nes_id)
    async with sm() as s:
        plat = await release_override(s, platform_id=nes_id)
    # The pack-applied source was 'community', so release reverts there.
    assert plat.pack_source == "community"

    async with sm() as s:
        formats = (
            (
                await s.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == nes_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert all(f.pack_source == "community" for f in formats)


@pytest.mark.asyncio
async def test_release_override_no_op_when_not_overridden(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)
    async with sm() as s:
        plat = await release_override(s, platform_id=nes_id)
    # Already 'community'; release is a no-op.
    assert plat.pack_source == "community"


# ---------------------------------------------------------------------------
# T041 — user-added formats survive a pack apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_added_format_survives_subsequent_pack_apply(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        await mark_overridden(s, platform_id=nes_id)
    async with sm() as s:
        await add_format(
            s, platform_id=nes_id, extension=".operator", format_type="cartridge"
        )

    # A subsequent pack apply on the same slug must short-circuit
    # (the platform is user-overridden) and preserve the user-added
    # format.
    new_body = (
        b"pack_version: '2026.05.001'\n"
        b"schema_version: 1\n"
        b"platforms:\n"
        b"  - slug: nes\n    name: NES\n    manufacturer: Nintendo\n"
        b"    formats:\n"
        b"      - extension: '.repacked'\n        format_type: cartridge\n"
    )
    async with sm() as s:
        await ingest_pack(
            s, sessionmaker=sm, content=new_body, source=_community()
        )

    async with sm() as s:
        formats = (
            (
                await s.execute(
                    select(PlatformFormat).where(
                        PlatformFormat.platform_id == nes_id
                    )
                )
            )
            .scalars()
            .all()
        )

    extensions = {f.extension for f in formats}
    assert ".operator" in extensions
    assert ".repacked" not in extensions  # the pack apply was short-circuited
    assert all(f.pack_source == "user" for f in formats)


# ---------------------------------------------------------------------------
# T042 — format mutation requires the platform be user-overridden
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_add_requires_override(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        with pytest.raises(OverrideRequiredError):
            await add_format(
                s, platform_id=nes_id, extension=".x", format_type="cartridge"
            )


@pytest.mark.asyncio
async def test_format_update_requires_override(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        fmt = (
            await s.execute(
                select(PlatformFormat).where(
                    PlatformFormat.platform_id == nes_id
                )
            )
        ).scalar_one()

    async with sm() as s:
        with pytest.raises(OverrideRequiredError):
            await update_format(s, format_id=fmt.id, format_type="archive")


@pytest.mark.asyncio
async def test_format_delete_requires_override(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)

    async with sm() as s:
        fmt = (
            await s.execute(
                select(PlatformFormat).where(
                    PlatformFormat.platform_id == nes_id
                )
            )
        ).scalar_one()

    async with sm() as s:
        with pytest.raises(OverrideRequiredError):
            await delete_format(s, format_id=fmt.id)


@pytest.mark.asyncio
async def test_format_update_works_when_overridden(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    sm = async_sessionmaker_factory
    nes_id = await _seed_minimal_pack(sm, pack_yaml)
    async with sm() as s:
        await mark_overridden(s, platform_id=nes_id)

    async with sm() as s:
        fmt = (
            await s.execute(
                select(PlatformFormat).where(
                    PlatformFormat.platform_id == nes_id
                )
            )
        ).scalar_one()
        updated = await update_format(
            s, format_id=fmt.id, max_size_bytes=10_000_000
        )
    assert updated.max_size_bytes == 10_000_000
    assert updated.pack_source == "user"


@pytest.mark.asyncio
async def test_format_delete_idempotent_miss(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    sm = async_sessionmaker_factory
    async with sm() as s:
        deleted = await delete_format(s, format_id=999_999)
    assert deleted is False
