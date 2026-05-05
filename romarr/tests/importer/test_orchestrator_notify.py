"""Orchestrator NOTIFY emission on auto-import success (slice 312).

When the orchestrator's auto-import path lands a successful
Dump, an ``OnImport`` event is published to the EventChannel
(when one is provided). The spec 011 dispatcher fans this out
to Apprise / Notifiarr / etc. so operators see "x imported"
notifications.

Best-effort emission: a publish failure must not invalidate
the committed import.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import (
    EventType,
    OnImportPayload,
)


@pytest.mark.asyncio
async def test_auto_import_emits_on_import_event(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When auto-import succeeds + an EventChannel is supplied,
    an OnImportPayload is published with fully-populated
    GameRef / ReleaseRef / DumpRef."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-notify",
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

    received: list[OnImportPayload] = []

    async def _capture(event):  # type: ignore[no-untyped-def]
        if event.event_type == EventType.ON_IMPORT:
            received.append(event)

    channel = EventChannel()
    await channel.start()
    channel.subscribe_global(_capture)

    try:
        context = ImportContext(
            source_path=rom,
            correlation_id=uuid4(),
            imported_via="manual",
        )
        outcome = await run_import(
            context, session=async_session, event_channel=channel
        )
        await channel.drain()
    finally:
        channel.unsubscribe_global(_capture)
        await channel.stop()

    assert outcome.success is True
    assert len(received) == 1
    event = received[0]
    assert event.game.id == game.id
    assert event.game.title == "Sonic the Hedgehog"
    assert event.game.platform_slug == "megadrive"
    assert event.release.id == release.id
    assert event.release.region == "USA"
    assert event.dump.path == str(rom)
    assert event.dump.sha1 is not None


@pytest.mark.asyncio
async def test_auto_import_succeeds_without_event_channel(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """``event_channel=None`` (the default) skips the publish
    step. Auto-import still commits its Dump + Release flip."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-no-channel",
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
    assert outcome.success is True
    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed.status == "imported"
