"""Orchestrator auto-import success path (slice 311).

When IDENTIFY's GAMEMATCH resolves to a confident monitored
Game AND that Game has exactly one wanted Release, the
orchestrator bypasses parking and runs an in-place import via
``manual_import_known``. The Dump row lands at the source
path (no MOVE step yet), the Release flips to ``imported``,
and the import_history row records ``success=True``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release, UnidentifiedDump
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_auto_import_when_game_match_resolves_to_one_wanted_release(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Header reads platform → fuzzy GAMEMATCH resolves to a
    monitored Game → that Game has exactly one wanted Release →
    orchestrator auto-imports in-place (no parking)."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-auto",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

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

    # Success path: outcome carries the canonical fields.
    assert outcome.success is True
    assert outcome.game_id == game.id
    assert outcome.release_id == release.id
    assert outcome.dump_id is not None

    # No parking happened.
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one_or_none()
    assert parked is None

    # Dump row landed in-place (no MOVE step yet).
    dump = (
        await async_session.execute(select(Dump).where(Dump.path == str(rom)))
    ).scalar_one()
    assert dump.release_id == release.id

    # Release flipped to imported.
    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed.status == "imported"

    # import_history row records success=True.
    history = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.id == outcome.history_id
            )
        )
    ).scalar_one()
    assert history.success is True


@pytest.mark.asyncio
async def test_auto_import_skipped_when_multiple_wanted_releases(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the matched Game has 2+ wanted Releases (USA + EUR
    variants), the auto-import gate doesn't fire — the operator
    has to pick which Release. The file is still parked with
    ``suggested_game_id`` populated."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-multi",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    for region in ["USA", "EUR"]:
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

    # Multi-Release ambiguity → fall through to parking.
    assert outcome.success is False
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.suggested_game_id == game.id
