"""Build a concrete :class:`DownloadClient` impl from a persisted row.

Single source of truth so the API routers + the future grab orchestrator
+ the connectivity tester all instantiate clients the same way.
Credentials are decrypted via :mod:`romarr.metadata.encryption` per
Article III (single Fernet helper across the project).

Slice 435 — ``GRABARR_DIRECT`` clients are cached as singletons per
``row.id`` because they hold their own in-memory state (the
``_pending`` dict tracking active http_direct streams + their
asyncio tasks). qBit / SAB don't need this: their state lives in
the external daemon, so every factory call freely builds a fresh
client. For ``grabarr_direct`` though, building a fresh instance
every time the queue reconciler polls means ``get_status`` raises
``unknown native_id`` immediately after add_torrent — the
download might land on disk via its still-running task but the
queue row stays stuck on "downloading" because nobody can see
into the pending dict the ephemeral instance carried.

Cache invalidation hooks below (``forget_grabarr_direct``) are
called from the PUT/DELETE handlers so config changes pick up
on the next factory call. Romarr restart drops the cache
entirely; in-flight downloads survive the restart on disk but
appear as "unknown" until R5 wires DB-backed state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from romarr.downloaders.implementations import (
    DelugeClient,
    GrabarrDirectClient,
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


# Slice 435 — singleton cache for grabarr_direct clients. Keyed by
# row.id; the value is the live client instance whose ``_pending``
# dict + asyncio tasks must survive across factory calls.
# ``forget_grabarr_direct(row_id)`` clears one entry; PUT/DELETE
# handlers call it so config changes take effect on the next
# factory call without a Romarr restart.
_grabarr_direct_cache: dict[int, "GrabarrDirectClient"] = {}


def forget_grabarr_direct(row_id: int) -> None:
    """Drop the cached singleton for ``row_id``.

    Called from the PUT + DELETE handlers in
    :mod:`romarr.downloaders.api.clients`. The next
    ``build_client_from_row`` call instantiates a fresh client with
    the updated config; any active stream tasks the old instance
    held are kept alive by the asyncio event loop until they
    complete on their own — they just won't be visible to the
    queue reconciler after the swap (acceptable trade-off; the
    operator who edits a download_client row is typically
    aware they're disrupting in-flight work).
    """
    _grabarr_direct_cache.pop(row_id, None)


def build_client_from_row(row: DownloadClientRow) -> DownloadClient:
    """Instantiate the right :class:`DownloadClient` for ``row``.

    The stub clients (Transmission/Deluge/NZBGet) are intentionally
    constructable so callers that ignore ``available=False`` get a
    consistent ``NotImplementedError("deferred to v1")`` rather than
    a ``KeyError``. The schema endpoint is what gates configuration.
    """
    ssl_setting = cast("SslCertValidation", row.ssl_cert_validation)
    if row.type == ClientType.QBITTORRENT.value:
        # Slice 379 — credentials optional (subnet auth-bypass).
        # The DB schema lets both columns be NULL; the
        # ``DownloadClientCreate`` validator already enforces
        # the "both or neither" invariant, so we only see one
        # of the two configured shapes here.
        password = (
            decrypt(row.password_encrypted).decode("utf-8")
            if row.password_encrypted is not None
            else ""
        )
        return QBittorrentClient(
            client_id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            username=row.username or "",
            password=password,
            use_ssl=row.use_ssl,
            url_base=row.url_base,
            ssl_cert_validation=ssl_setting,
            category_default=row.category_default,
            timeout_seconds=row.timeout_seconds,
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
            timeout_seconds=row.timeout_seconds,
        )
    if row.type == ClientType.TRANSMISSION.value:
        return TransmissionClient(client_id=row.id, name=row.name)
    if row.type == ClientType.DELUGE.value:
        # Deluge n'a pas de username — l'auth WebUI = password seul.
        # Le champ ``password_encrypted`` de la row porte donc le
        # password du WebUI (pas du daemon RPC, une confusion classique).
        if row.password_encrypted is None:
            raise ValueError(f"Deluge row {row.id} is missing WebUI password")
        password = decrypt(row.password_encrypted).decode("utf-8")
        return DelugeClient(
            client_id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            password=password,
            use_ssl=row.use_ssl,
            url_base=row.url_base,
            ssl_cert_validation=ssl_setting,
            category_default=row.category_default,
            timeout_seconds=row.timeout_seconds,
        )
    if row.type == ClientType.NZBGET.value:
        return NzbgetClient(client_id=row.id, name=row.name)
    if row.type == ClientType.GRABARR_DIRECT.value:
        # Slice 435 — singleton cache: the in-memory _pending dict +
        # asyncio stream tasks must survive across factory calls so
        # the queue reconciler can see the state add_torrent created.
        existing = _grabarr_direct_cache.get(row.id)
        if existing is not None:
            return existing
        # Slice 424 — the api_key column carries the Grabarr apikey
        # (same key the linked indexer row uses against the Torznab
        # surface, per the v0.2 doc's "Romarr-side topology"). It's
        # NOT NULL once the wizard lands, but until then we tolerate
        # absence on the foundation row and let test_connection
        # surface the 401.
        api_key = (
            decrypt(row.api_key_encrypted).decode("utf-8")
            if row.api_key_encrypted is not None
            else ""
        )
        client = GrabarrDirectClient(
            client_id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            api_key=api_key,
            use_ssl=row.use_ssl,
            url_base=row.url_base,
            ssl_cert_validation=ssl_setting,
            category_default=row.category_default,
            timeout_seconds=row.timeout_seconds,
            # Slice 427 / R3a — prefer the per-row override (set by
            # the wizard); fall back to env / ``/downloads`` when
            # NULL. The client constructor reads the env var so
            # passing ``None`` keeps the fallback chain intact.
            download_root=row.download_root,
        )
        _grabarr_direct_cache[row.id] = client
        return client
    raise ValueError(f"unknown download client type: {row.type!r}")


__all__ = ["build_client_from_row", "forget_grabarr_direct"]
