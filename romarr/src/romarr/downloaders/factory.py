"""Build a concrete :class:`DownloadClient` impl from a persisted row.

Single source of truth so the API routers + the future grab orchestrator
+ the connectivity tester all instantiate clients the same way.
Credentials are decrypted via :mod:`romarr.metadata.encryption` per
Article III (single Fernet helper across the project).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from romarr.downloaders.implementations import (
    DelugeClient,
    NzbgetClient,
    QBittorrentClient,
    SabnzbdClient,
    TransmissionClient,
)
from romarr.downloaders.types import ClientType
from romarr.metadata.encryption import decrypt

if TYPE_CHECKING:
    from romarr.downloaders.base import DownloadClient
    from romarr.downloaders.models import DownloadClient as DownloadClientRow
    from romarr.downloaders.tls import SslCertValidation


def build_client_from_row(row: DownloadClientRow) -> DownloadClient:
    """Instantiate the right :class:`DownloadClient` for ``row``.

    The stub clients (Transmission/Deluge/NZBGet) are intentionally
    constructable so callers that ignore ``available=False`` get a
    consistent ``NotImplementedError("deferred to v1")`` rather than
    a ``KeyError``. The schema endpoint is what gates configuration.
    """
    ssl_setting = cast("SslCertValidation", row.ssl_cert_validation)
    if row.type == ClientType.QBITTORRENT.value:
        if row.password_encrypted is None or row.username is None:
            raise ValueError(
                f"qBittorrent row {row.id} is missing username/password"
            )
        password = decrypt(row.password_encrypted).decode("utf-8")
        return QBittorrentClient(
            client_id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            username=row.username,
            password=password,
            use_ssl=row.use_ssl,
            url_base=row.url_base,
            ssl_cert_validation=ssl_setting,
            category_default=row.category_default,
        )
    if row.type == ClientType.SABNZBD.value:
        if row.api_key_encrypted is None:
            raise ValueError(f"SABnzbd row {row.id} is missing api_key")
        api_key = decrypt(row.api_key_encrypted).decode("utf-8")
        return SabnzbdClient(
            client_id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            api_key=api_key,
            use_ssl=row.use_ssl,
            url_base=row.url_base,
            ssl_cert_validation=ssl_setting,
            category_default=row.category_default,
        )
    if row.type == ClientType.TRANSMISSION.value:
        return TransmissionClient(client_id=row.id, name=row.name)
    if row.type == ClientType.DELUGE.value:
        return DelugeClient(client_id=row.id, name=row.name)
    if row.type == ClientType.NZBGET.value:
        return NzbgetClient(client_id=row.id, name=row.name)
    raise ValueError(f"unknown download client type: {row.type!r}")


__all__ = ["build_client_from_row"]
