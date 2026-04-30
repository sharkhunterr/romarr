"""Transmission client — stub, deferred to v1."""

from __future__ import annotations

from typing import ClassVar

from romarr.downloaders.implementations._stub import _StubClient
from romarr.downloaders.types import ClientType


class TransmissionClient(_StubClient):
    """Transmission torrent client — implementation deferred to v1."""

    client_type: ClassVar[ClientType] = ClientType.TRANSMISSION
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False


__all__ = ["TransmissionClient"]
