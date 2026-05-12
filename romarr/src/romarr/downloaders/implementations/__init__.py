"""Concrete download-client implementations.

Slice 1 ships only the three v1-deferred stubs (Transmission,
Deluge, NZBGet). Each raises :class:`NotImplementedError` from every
method except the class-level metadata attributes. qBittorrent +
SABnzbd land in slice 2. Slice 422 adds the Grabarr-direct
foundation stub (``available = False`` until the R2 wiring slice).
"""

from romarr.downloaders.implementations.deluge import DelugeClient
from romarr.downloaders.implementations.grabarr_direct import (
    GrabarrDirectClient,
)
from romarr.downloaders.implementations.nzbget import NzbgetClient
from romarr.downloaders.implementations.qbittorrent import QBittorrentClient
from romarr.downloaders.implementations.sabnzbd import SabnzbdClient
from romarr.downloaders.implementations.transmission import TransmissionClient

__all__ = [
    "DelugeClient",
    "GrabarrDirectClient",
    "NzbgetClient",
    "QBittorrentClient",
    "SabnzbdClient",
    "TransmissionClient",
]
