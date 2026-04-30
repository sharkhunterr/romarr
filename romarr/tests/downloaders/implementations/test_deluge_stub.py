"""Deluge stub tests (T041)."""

from __future__ import annotations

import pytest

from romarr.downloaders.implementations.deluge import DelugeClient
from romarr.downloaders.types import ClientType, TorrentMagnet


def test_class_metadata() -> None:
    assert DelugeClient.client_type is ClientType.DELUGE
    assert DelugeClient.supports_torrents is True
    assert DelugeClient.supports_usenet is False
    assert DelugeClient.available is False


async def test_methods_raise_deferred() -> None:
    client = DelugeClient(client_id=2, name="Stub")
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.test_connection()
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.add_torrent(
            TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:def"),
            category="romarr",
            tags=["romarr"],
        )
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.remove("hash", delete_files=False)
