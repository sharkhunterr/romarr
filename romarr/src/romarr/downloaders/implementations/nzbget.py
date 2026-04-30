"""NZBGet client — stub, deferred to v1."""

from __future__ import annotations

from typing import ClassVar

from romarr.downloaders.implementations._stub import _StubClient
from romarr.downloaders.types import ClientType


class NzbgetClient(_StubClient):
    """NZBGet Usenet client — implementation deferred to v1."""

    client_type: ClassVar[ClientType] = ClientType.NZBGET
    supports_torrents: ClassVar[bool] = False
    supports_usenet: ClassVar[bool] = True


__all__ = ["NzbgetClient"]
