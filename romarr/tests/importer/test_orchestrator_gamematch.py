"""Orchestrator GAMEMATCH fuzzy resolution (slice 310).

Slice 310 wires spec 008's ``match_to_game`` fuzzy matcher into
the orchestrator's IDENTIFY enrichment. When we have a
platform_id + at least one title (parsed filename or DAT entry
name), the fuzzy matcher resolves to either a monitored Game
(``game_id`` field) or an unmonitored suggestion
(``suggested_game_id`` field) — either populates the parked
row.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform, UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_fuzzy_match_skips_unrelated_titles(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Game title "Sonic the Hedgehog" + filename parses to
    "Mortal Kombat" → RapidFuzz at the 90 threshold rejects the
    pair; ``suggested_game_id`` stays None even though the
    platform was pinned by the header read."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-fuzzy",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()

    rom = tmp_path / "downloads" / "Mortal Kombat (USA).bin"
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
    await run_import(context, session=async_session)

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    # Header read pinned the platform.
    assert parked.suggested_platform_id == platform.id
    # Unrelated titles → no game suggestion.
    assert parked.suggested_game_id is None


@pytest.mark.asyncio
async def test_fuzzy_match_resolves_unmonitored_as_suggestion(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Unmonitored Game with a high-confidence title match
    surfaces as ``suggested_game_id`` per FR-016."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-um",
        title="Sonic the Hedgehog",
        monitored=False,
    )
    async_session.add(game)
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
    await run_import(context, session=async_session)

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.suggested_platform_id == platform.id
    # Unmonitored Game with exact title match → unmonitored
    # candidate at the 95-threshold suggested-pool path → fills
    # suggested_game_id (not game_id, since the game isn't
    # monitored).
    assert parked.suggested_game_id == game.id
