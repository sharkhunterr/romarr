"""End-to-end auto-import smoke (spec 008 T081 / SC-001).

Validates the full happy path the operator actually sees:

  1. Watcher dispatches a downloaded ROM with a download
     client + native id in the import context.
  2. Orchestrator hashes → IDENTIFY (header pins platform) →
     GAMEMATCH (DAT lookup resolves Game) → auto-imports.
  3. Dump persists, Release flips to ``imported``,
     ``set_imported_tag`` fires on the origin qBit client,
     and ``OnImport`` lands on the EventChannel.

The test exercises slices 307-313 in one path. Marked T081
because it's the documented end-to-end smoke for the
torrent flow (US1, SC-001).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import EventType, OnImportPayload


@pytest.mark.asyncio
async def test_end_to_end_torrent_flow_lights_up_every_step(
    async_session: AsyncSession, tmp_path: Path, monkeypatch
) -> None:
    """T081 — Full torrent-flow auto-import smoke."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-secret-e2e")
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    # 1. Seed a qBit DownloadClient row.
    from romarr.metadata.encryption import encrypt

    qbit = DownloadClientRow(
        name="qBit",
        type="qbittorrent",
        host="localhost",
        port=8080,
        url_base="",
        use_ssl=False,
        username="admin",
        password_encrypted=encrypt(b"adminadmin"),
        ssl_cert_validation="enabled",
        category_default="romarr",
        priority=10,
        enable_for_torrents=True,
        enable_for_usenet=False,
        enabled=True,
    )
    async_session.add(qbit)
    await async_session.commit()
    await async_session.refresh(qbit)

    # 2. Seed Mega Drive platform + Game + wanted Release.
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-e2e",
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

    # 3. Drop a fake Mega Drive ROM in a "downloads" folder.
    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    # 4. Capture set_imported_tag calls + OnImport events.
    from romarr.downloaders.implementations.qbittorrent import (
        QBittorrentClient,
    )

    tag_calls: list[str] = []

    async def _fake_tag(self: Any, native_id: str) -> None:  # noqa: ARG001
        tag_calls.append(native_id)

    monkeypatch.setattr(
        QBittorrentClient, "set_imported_tag", _fake_tag
    )

    received_events: list[OnImportPayload] = []

    async def _capture(event):  # type: ignore[no-untyped-def]
        if event.event_type == EventType.ON_IMPORT:
            received_events.append(event)

    channel = EventChannel()
    await channel.start()
    channel.subscribe_global(_capture)

    try:
        # 5. Run the orchestrator with the full context shape
        # (download_client_id + native_id + event_channel) the
        # production watcher dispatcher constructs.
        context = ImportContext(
            source_path=rom,
            correlation_id=uuid4(),
            imported_via="automatic",
            download_client_id=qbit.id,
            download_client_native_id="info-hash-deadbeef",
        )
        outcome = await run_import(
            context, session=async_session, event_channel=channel
        )
        await channel.drain()
    finally:
        channel.unsubscribe_global(_capture)
        await channel.stop()

    # 6. Verify every step landed:

    # Outcome carries the canonical fields.
    assert outcome.success is True
    assert outcome.game_id == game.id
    assert outcome.release_id == release.id
    assert outcome.dump_id is not None

    # Dump row landed at the source path (in-place — no MOVE yet).
    dump = (
        await async_session.execute(
            select(Dump).where(Dump.id == outcome.dump_id)
        )
    ).scalar_one()
    assert dump.release_id == release.id
    assert dump.path == str(rom)
    assert Path(dump.path).exists()

    # Release transitioned to imported.
    refreshed_release = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed_release.status == "imported"

    # qBit set_imported_tag fired exactly once with the native_id.
    assert tag_calls == ["info-hash-deadbeef"]

    # OnImport event emitted with full payload.
    assert len(received_events) == 1
    event = received_events[0]
    assert event.game.id == game.id
    assert event.release.id == release.id
    assert event.dump.path == str(rom)

    # import_history records success.
    history = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.id == outcome.history_id
            )
        )
    ).scalar_one()
    assert history.success is True
    assert history.game_id == game.id
    assert history.release_id == release.id
    assert history.imported_via == "automatic"
