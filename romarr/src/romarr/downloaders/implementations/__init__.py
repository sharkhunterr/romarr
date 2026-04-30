"""Concrete download-client implementations.

Slice 1 ships only the three v1-deferred stubs (Transmission,
Deluge, NZBGet). Each raises :class:`NotImplementedError` from every
method except the class-level metadata attributes. qBittorrent +
SABnzbd land in slice 2.
"""

from romarr.downloaders.implementations.deluge import DelugeClient
from romarr.downloaders.implementations.nzbget import NzbgetClient
from romarr.downloaders.implementations.transmission import TransmissionClient

__all__ = ["DelugeClient", "NzbgetClient", "TransmissionClient"]
