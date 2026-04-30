"""Transmission stub tests (T040)."""

from __future__ import annotations

import pytest

from romarr.downloaders.implementations.transmission import TransmissionClient
from romarr.downloaders.types import (
    ClientType,
    NzbUrl,
    TorrentMagnet,
)


def test_class_metadata() -> None:
    assert TransmissionClient.client_type is ClientType.TRANSMISSION
    assert TransmissionClient.supports_torrents is True
    assert TransmissionClient.supports_usenet is False
    assert TransmissionClient.available is False


async def test_every_method_raises_deferred() -> None:
    client = TransmissionClient(client_id=1, name="Stub")

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.test_connection()

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.add_torrent(
            TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:abc"),
            category="romarr",
            tags=["romarr"],
        )

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.add_nzb(
            NzbUrl(url="http://example.test/file.nzb"),  # type: ignore[arg-type]
            category="romarr",
        )

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.get_status("info-hash-abc")

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.remove("info-hash-abc", delete_files=True)

    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.set_imported_tag("info-hash-abc")
