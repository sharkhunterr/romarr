"""Grabarr-direct foundation stub tests (slice 422).

Locks in the class-level metadata + the ``deferred to v1`` contract.
The actual wiring (resolve dispatcher, http-direct streamer, qBit
delegation) lands in the R2 slice — these tests will be superseded
once the stub becomes a real implementation.
"""

from __future__ import annotations

import pytest

from romarr.downloaders.implementations.grabarr_direct import (
    GrabarrDirectClient,
)
from romarr.downloaders.types import (
    ClientType,
    NzbUrl,
    TorrentMagnet,
)


def test_class_metadata() -> None:
    assert GrabarrDirectClient.client_type is ClientType.GRABARR_DIRECT
    assert GrabarrDirectClient.supports_torrents is True
    assert GrabarrDirectClient.supports_usenet is False
    # Foundation slice ships with available=False so the UI does not
    # list the type in the Add Download Client modal yet — the R2
    # "Add Grabarr" wizard creates the row through a dedicated path.
    assert GrabarrDirectClient.available is False


def test_client_type_value_matches_check_constraint() -> None:
    # Migration 0022 widened the CHECK constraint to include exactly
    # this literal — keep the StrEnum value pinned so future rename
    # attempts trip this assert before they trip the DB.
    assert ClientType.GRABARR_DIRECT.value == "grabarr_direct"


async def test_every_method_raises_deferred() -> None:
    client = GrabarrDirectClient(client_id=1, name="Grabarr")

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
