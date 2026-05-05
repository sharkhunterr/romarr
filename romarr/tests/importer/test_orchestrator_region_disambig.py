"""Multi-Release region disambiguation (slice 315).

When the matched Game has multiple wanted Releases (e.g., USA +
EUR variants), the orchestrator parses the filename for region
tags and picks the Release whose regions tuple overlaps with
the parser's. Single-overlap → auto-import fires against that
Release; zero or multi-overlap → fall through to parking.

Slice 314's behavior (multi-Release ambiguity → parking) is
preserved when overlap can't be computed (mismatched region
encoding). The disambiguation only kicks in when both sides use
the same encoding (parser emits ISO-3166-1 alpha-2 codes —
"US", "EU", "JP", "WW" — so Release.regions populated with the
same codes will overlap cleanly).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release, UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_multi_release_region_overlap_picks_one(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Two wanted Releases (US + EU) + filename parses to US →
    auto-import fires against the US Release."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-region",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    # ISO-3166-1 alpha-2 codes — same encoding the parser emits.
    us_release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["US"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
    )
    eu_release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (Europe)",
        regions=["EU"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
    )
    async_session.add_all([us_release, eu_release])
    await async_session.commit()
    await async_session.refresh(us_release)
    await async_session.refresh(eu_release)

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
    assert outcome.release_id == us_release.id


@pytest.mark.asyncio
async def test_multi_release_no_region_overlap_falls_through(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Two wanted Releases (JP + KR) + filename parses to US →
    no region overlap → fall through to parking."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-no-overlap",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    for region in ["JP", "KR"]:
        async_session.add(
            Release(
                game_id=game.id,
                name=f"Sonic the Hedgehog ({region})",
                regions=[region],
                languages=["en"],
                dump_status=DumpStatus.VERIFIED,
                naming_convention=NamingConvention.NO_INTRO,
                status="wanted",
            )
        )
    await async_session.commit()

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    # No overlap → multi-Release ambiguity stands → park.
    assert outcome.success is False
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.suggested_game_id == game.id
