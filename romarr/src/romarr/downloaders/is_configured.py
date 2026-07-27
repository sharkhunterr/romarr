"""Single source of truth for ``DownloadClient.is_configured``.

Truth: a client is "configured" when its row carries the credential
its type requires. Different types require different columns —
qBit / Deluge take a password (though qBit's subnet-auth-bypass
lets it run credentialless), SAB / Grabarr take an api_key, the
stub types (Transmission, NZBGet) can't be configured at all yet.

Kept out of the API projector so the routing layer can call it
without pulling in FastAPI + Pydantic response models.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from romarr.downloaders.types import ClientType

if TYPE_CHECKING:
    from romarr.downloaders.models import DownloadClient


def is_client_configured(row: DownloadClient) -> bool:
    """Return True iff ``row`` carries the credential its type expects.

    Type-specific rules (mirrors :func:`factory.build_client_from_row`):

      * ``qbittorrent`` — password OR treated as "subnet auth bypass"
        (empty creds intentional). Return True in both cases so a
        WebUI mounted on a trusted subnet still gets routed to.
      * ``deluge`` — password REQUIRED (WebUI has no
        credentialless mode).
      * ``sabnzbd`` — api_key REQUIRED.
      * ``grabarr_direct`` — api_key REQUIRED (the 401 branch on
        an empty key is a hard-fail loop for auto-grab).
      * ``transmission`` / ``nzbget`` — stubs, always False.
    """
    t = row.type
    if t == ClientType.QBITTORRENT.value:
        # Subnet-auth-bypass is a valid deployment; treat empty as OK.
        return True
    if t == ClientType.DELUGE.value:
        return row.password_encrypted is not None
    if t == ClientType.SABNZBD.value:
        return row.api_key_encrypted is not None
    if t == ClientType.GRABARR_DIRECT.value:
        return row.api_key_encrypted is not None
    # transmission, nzbget: deferred to v1.
    return False


__all__ = ["is_client_configured"]
