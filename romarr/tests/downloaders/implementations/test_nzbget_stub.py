"""NZBGet stub tests (T042)."""

from __future__ import annotations

import pytest

from romarr.downloaders.implementations.nzbget import NzbgetClient
from romarr.downloaders.types import ClientType, NzbUrl


def test_class_metadata() -> None:
    assert NzbgetClient.client_type is ClientType.NZBGET
    assert NzbgetClient.supports_torrents is False
    assert NzbgetClient.supports_usenet is True
    assert NzbgetClient.available is False


async def test_methods_raise_deferred() -> None:
    client = NzbgetClient(client_id=3, name="Stub")
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.test_connection()
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.add_nzb(
            NzbUrl(url="http://example.test/file.nzb"),  # type: ignore[arg-type]
            category="romarr",
        )
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await client.get_status("nzo-id")
