"""Orchestrator LIFECYCLE tagging on auto-import success (slice 313).

When auto-import succeeds AND the import context carries a
download client + native id, the orchestrator calls
``set_imported_tag`` on the matching client so the operator's
qBit / SAB UI shows the ``romarr-imported`` tag (FR-013).

Best-effort: a tagging failure must not invalidate the
committed import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


async def _seed_qbit_row(session: AsyncSession) -> int:
    """Seed a minimal qBit DownloadClient row + return its id."""
    from romarr.metadata.encryption import encrypt

    row = DownloadClientRow(
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
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row.id


async def _seed_game_release(
    session: AsyncSession,
) -> tuple[Game, Release]:
    platform = Platform(slug="megadrive", name="Mega Drive")
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-tag",
        title="Sonic the Hedgehog",
        monitored=True,
    )
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
    return game, release


def _write_megadrive_rom(tmp_path: Path) -> Path:
    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))
    return rom


@pytest.mark.asyncio
async def test_auto_import_calls_set_imported_tag_on_origin_client(
    async_session: AsyncSession, tmp_path: Path, monkeypatch
) -> None:
    """Successful auto-import + context with download_client_id +
    native_id → orchestrator calls ``set_imported_tag(native_id)``
    on the resolved client impl."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY", "test-secret-for-encrypt"
    )
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    client_id = await _seed_qbit_row(async_session)
    _, _ = await _seed_game_release(async_session)

    rom = _write_megadrive_rom(tmp_path)

    # Patch ``set_imported_tag`` at the QBittorrentClient class
    # level so the test doesn't make real HTTP calls.
    from romarr.downloaders.implementations.qbittorrent import (
        QBittorrentClient,
    )

    captured: list[str] = []

    async def _fake_tag(self: Any, native_id: str) -> None:  # noqa: ARG001
        captured.append(native_id)

    monkeypatch.setattr(
        QBittorrentClient, "set_imported_tag", _fake_tag
    )

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="automatic",
        download_client_id=client_id,
        download_client_native_id="info-hash-deadbeef",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
    assert captured == ["info-hash-deadbeef"]


@pytest.mark.asyncio
async def test_auto_import_skips_tagging_when_no_origin_client(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Manual flow (no download_client_id/native_id in context) →
    no tagging attempt; auto-import still succeeds."""
    _, _ = await _seed_game_release(async_session)
    rom = _write_megadrive_rom(tmp_path)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True


@pytest.mark.asyncio
async def test_tag_failure_does_not_invalidate_import(
    async_session: AsyncSession, tmp_path: Path, monkeypatch
) -> None:
    """``set_imported_tag`` raises → orchestrator catches +
    swallows the exception; the committed import stays
    successful."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY", "test-secret-for-encrypt"
    )
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    client_id = await _seed_qbit_row(async_session)
    _, _ = await _seed_game_release(async_session)
    rom = _write_megadrive_rom(tmp_path)

    from romarr.downloaders.implementations.qbittorrent import (
        QBittorrentClient,
    )

    async def _raise(self: Any, native_id: str) -> None:  # noqa: ARG001
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(QBittorrentClient, "set_imported_tag", _raise)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="automatic",
        download_client_id=client_id,
        download_client_native_id="info-hash-cafef00d",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
