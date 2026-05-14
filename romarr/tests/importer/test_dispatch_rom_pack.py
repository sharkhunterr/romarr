"""Watcher → ROM-pack routing tests (slice 463).

When a completed download is bound to a ``grab``-sourced
:class:`RomPack`, the watcher dispatcher routes it to the pack
ingest pipeline instead of the single-file importer.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.api.models import QueueEntry
from romarr.domain.models import RomPack
from romarr.downloaders.models import DownloadClient
from romarr.downloaders.types import ManagedDownload
from romarr.importer import _dispatch


async def _seed_client(session: AsyncSession) -> int:
    """Seed the ``download_client`` row the QueueEntry FK needs."""
    client = DownloadClient(
        name="qbit", type="qbittorrent", host="localhost", port=8080
    )
    session.add(client)
    await session.flush()
    return client.id


def _item(client_id: int = 1, native_id: str = "hash-abc") -> ManagedDownload:
    return ManagedDownload(
        client_id=client_id,
        client_native_id=native_id,
        name="No-Intro GBA pack",
        save_path="/downloads/gba-pack",
    )


@pytest.mark.asyncio
async def test_returns_false_for_ordinary_download(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No matching grab pack → the helper declines and the normal
    importer path takes over."""
    handled = await _dispatch._maybe_route_to_rom_pack(
        async_sessionmaker_factory, _item(), "/downloads/some-rom.zip"
    )
    assert handled is False


@pytest.mark.asyncio
async def test_routes_pending_grab_pack_to_ingest(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pending grab pack: the helper records the save_path,
    settles the queue_entry, and fires ``ingest_rom_pack``."""
    sm = async_sessionmaker_factory
    async with sm() as session:
        client_id = await _seed_client(session)
        pack = RomPack(
            name="GBA pack",
            source_kind="grab",
            download_client_id=client_id,
            download_client_native_id="hash-abc",
            status="pending",
        )
        session.add(pack)
        session.add(
            QueueEntry(
                download_client_id=client_id,
                download_client_native_id="hash-abc",
                title="GBA pack",
                state="downloading",
                progress=1.0,
            )
        )
        await session.commit()
        pack_id = pack.id

    ingest_calls: list[int] = []

    async def _fake_ingest(*, sessionmaker: object, rom_pack_id: int) -> None:
        ingest_calls.append(rom_pack_id)

    monkeypatch.setattr(_dispatch, "ingest_rom_pack", _fake_ingest)

    handled = await _dispatch._maybe_route_to_rom_pack(
        sm, _item(client_id=client_id), "/downloads/gba-pack"
    )
    assert handled is True
    # Let the detached ingest task run.
    await asyncio.sleep(0)
    assert ingest_calls == [pack_id]

    async with sm() as session:
        pack = (
            await session.execute(
                select(RomPack).where(RomPack.id == pack_id)
            )
        ).scalar_one()
        assert pack.downloaded_path == "/downloads/gba-pack"
        # The completed download settles the queue_entry clean.
        qe = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_id == client_id
                )
            )
        ).scalar_one_or_none()
        assert qe is None


@pytest.mark.asyncio
async def test_already_started_pack_does_not_re_ingest(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A watcher re-tick after a restart sees a non-pending pack
    and re-settles the queue_entry without firing a second
    ingest."""
    sm = async_sessionmaker_factory
    async with sm() as session:
        pack = RomPack(
            name="GBA pack",
            source_kind="grab",
            download_client_id=1,
            download_client_native_id="hash-abc",
            status="importing",
            downloaded_path="/downloads/gba-pack",
        )
        session.add(pack)
        await session.commit()

    ingest_calls: list[int] = []

    async def _fake_ingest(*, sessionmaker: object, rom_pack_id: int) -> None:
        ingest_calls.append(rom_pack_id)

    monkeypatch.setattr(_dispatch, "ingest_rom_pack", _fake_ingest)

    handled = await _dispatch._maybe_route_to_rom_pack(
        sm, _item(), "/downloads/gba-pack"
    )
    assert handled is True
    await asyncio.sleep(0)
    assert ingest_calls == []
