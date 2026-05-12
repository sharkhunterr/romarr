"""Grabarr-direct client — foundation stub.

Wires :class:`romarr.downloaders.types.ClientType.GRABARR_DIRECT` into
the implementation registry so the factory imports cleanly and any
future row of ``download_client.type = 'grabarr_direct'`` (slice 422
widened the CHECK constraint) can resolve to a class.

The real implementation lands in the R2 wiring phase — it will:

- ``test_connection`` → ``GET /romarr/api/v1/health`` on the operator's
  Grabarr instance, validating the ``protocol_version``.
- ``add_torrent`` → extract the search-result token from the Torznab
  ``/download/{token}.torrent`` URL Romarr received from the indexer
  search, ``GET /romarr/api/v1/resolve/{token}``, dispatch per the
  ``method`` field (``http_direct`` streams via httpx; the two
  ``torrent_*`` variants delegate to the operator's qBit client and
  apply qBit ``filePrio`` for the meta-torrent case).

Until then this stub raises the standard ``deferred to v1`` message
so any caller wired up by accident fails loudly instead of silently.
``available = False`` (inherited from :class:`_StubClient`) keeps the
type out of the UI's ``_CLIENT_TYPES`` array — the "Add Grabarr"
wizard in R2 will flip this on and bypass the array entirely.

See ``docs/grabarr-direct-protocol.md`` (v0.2) for the full design.
"""

from __future__ import annotations

from typing import ClassVar

from romarr.downloaders.implementations._stub import _StubClient
from romarr.downloaders.types import ClientType


class GrabarrDirectClient(_StubClient):
    """Grabarr-direct client — wiring deferred to the R2 slice."""

    client_type: ClassVar[ClientType] = ClientType.GRABARR_DIRECT
    # Capability flags reflect the *target* behaviour: HTTP-direct
    # streaming counts as a "torrent-source" replacement (it consumes
    # a TorrentUrl source produced by the Torznab search adapter and
    # turns it into a managed download). Usenet is not in scope —
    # Grabarr does not expose NZB sources.
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False


__all__ = ["GrabarrDirectClient"]
