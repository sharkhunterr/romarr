"""Grabarr-direct client — slice 424 protocol-wiring implementation.

Talks to the matching Grabarr deploy's ``/romarr/api/v1/*`` surface
(slices 422 + 423 on the Grabarr side). For each grabbed release:

1. Romarr's search dispatcher picks this client because the
   originating indexer's ``implementation == 'grabarr'`` and the
   ``indexer.download_client_id`` is pinned to a row of this type.
2. ``add_torrent`` receives the Torznab enclosure URL
   (``/torznab/{slug}/download/{token}.torrent``) the indexer search
   already produced. We parse the ``{slug}`` + ``{token}`` and call
   ``GET /romarr/{slug}/api/v1/resolve/{token}`` against the
   configured Grabarr base.
3. The resolve response discriminates by ``method``:

   - ``http_direct``    — store the upstream URL + headers + size +
     filename in an in-memory pending dict keyed by a deterministic
     ``native_id``. **R2d** wires the actual httpx streamer + disk
     write + progress tracking + importer handoff; this slice only
     proves the protocol round-trips.
   - ``torrent_magnet`` — raises :class:`NotImplementedError` for
     now. **R2d** delegates to the operator's configured qBit row by
     re-invoking the routing engine with the magnet URL as the
     source kind. Operators with no qBit configured will see
     ``no_eligible_client`` post-R2d for the magnet branches —
     that filter happens in the search-results UI per the v0.2
     doc's "Romarr-side behaviour" section.

Keeps ``available = False`` so the Add Download Client modal does
not surface this type yet — the "Add Grabarr" wizard (R3) is the
only intended creation path. Operators wiring rows directly via
the API today get a fully constructable client that exercises
the protocol but does not actually transfer bytes.

See ``docs/grabarr-direct-protocol.md`` (v0.2.1) for the full
contract.
"""

from __future__ import annotations

import logging
import re
import ssl
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.errors import (
    AuthError,
    ConnectionError as DownloaderConnError,
    DownloaderError,
    TLSError,
    VersionError,
)
from romarr.downloaders.tags import TAG_ROMARR
from romarr.downloaders.tls import SslCertValidation, build_httpx_verify
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    DownloadStatus,
    ManagedDownload,
    NzbSource,
    TorrentBytes,
    TorrentMagnet,
    TorrentSource,
    TorrentUrl,
)

_log = logging.getLogger(__name__)

# Romarr refuses to talk to a Grabarr running a protocol_version
# this client wasn't designed against. Bump alongside any breaking
# change in the v0.2 doc's response shapes. ``test_connection``
# enforces this at config-test time so misconfiguration surfaces
# before any grab.
SUPPORTED_PROTOCOL_VERSION = 1

# ``/torznab/{slug}/download/{token}.torrent`` — the URL shape
# Grabarr already serialises into its Newznab enclosures. We extract
# the slug + token here rather than carrying them through a richer
# source type so the existing search → dispatch wiring stays generic
# (TorrentUrl is what every Torznab indexer produces).
_TORZNAB_DOWNLOAD_RE = re.compile(
    r"/torznab/(?P<slug>[^/]+)/download/(?P<token>[^/]+?)(?:\.torrent)?$"
)


class GrabarrDirectClient(DownloadClient):
    """Direct-protocol client backing ``ClientType.GRABARR_DIRECT``.

    This slice (R2c) ships test_connection + the resolve protocol
    wiring. Actual disk transfers (http_direct) + qBit delegation
    (torrent_magnet) land in R2d — ``add_torrent`` returns a native
    id immediately after a successful ``/resolve`` round-trip so
    the dispatcher's queue-entry mirror is exercised end-to-end.
    """

    client_type: ClassVar[ClientType] = ClientType.GRABARR_DIRECT
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False
    # R3 wizard flips this on. Until then the type stays out of the
    # Add Download Client modal's ``_CLIENT_TYPES`` array.
    available: ClassVar[bool] = False

    def __init__(
        self,
        *,
        client_id: int,
        name: str,
        host: str,
        port: int,
        api_key: str,
        use_ssl: bool = False,
        url_base: str | None = None,
        ssl_cert_validation: SslCertValidation = "enabled",
        category_default: str = TAG_ROMARR,
        timeout_seconds: float = 60.0,
    ) -> None:
        super().__init__(client_id=client_id, name=name)
        self._host = host
        self._port = port
        self._api_key = api_key
        self._scheme = "https" if use_ssl else "http"
        self._url_base = (url_base or "").rstrip("/")
        self._verify = build_httpx_verify(ssl_cert_validation, host)
        self._category = category_default
        self._timeout = timeout_seconds
        # native_id -> resolve-response snapshot (method + url +
        # filename + size + headers + checksums). R2d turns this
        # into a backed-by-disk progress dict; for now it just lets
        # ``get_status`` and ``remove`` see the entries we just added.
        self._pending: dict[str, dict[str, Any]] = {}

    # ---- HTTP plumbing ------------------------------------------------------

    @property
    def base_url(self) -> str:
        """Fully-qualified ``/romarr`` root on the operator's Grabarr."""
        return f"{self._scheme}://{self._host}:{self._port}{self._url_base}"

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=self._verify,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    # ---- DownloadClient contract --------------------------------------------

    async def test_connection(self) -> str:
        """Probe Grabarr's ``/romarr/api/v1/health`` endpoint.

        Returns Grabarr's reported app version on success. Raises
        :class:`VersionError` on protocol_version mismatch — the
        operator must either upgrade Grabarr or downgrade Romarr
        before the integration will work.
        """
        url = f"{self.base_url}/romarr/api/v1/health"
        try:
            # The endpoint is unauthenticated, so we don't actually
            # need the Bearer header here — but using the same client
            # keeps the TLS / timeout settings uniform with /resolve
            # so a misconfigured proxy fails on the connectivity test
            # rather than later on a real grab.
            async with self._new_client() as client:
                resp = await client.get(url)
        except httpx.ConnectError as exc:
            raise DownloaderConnError(f"cannot reach Grabarr at {url}: {exc}") from exc
        except (httpx.PoolTimeout, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            raise DownloaderConnError(f"timeout reaching Grabarr at {url}: {exc}") from exc
        except ssl.SSLError as exc:
            raise TLSError(f"TLS handshake failed against {url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DownloaderConnError(f"HTTP error against {url}: {exc}") from exc

        if resp.status_code == 401:
            raise AuthError("Grabarr rejected the apikey on /health")
        if resp.status_code >= 500:
            raise DownloaderConnError(
                f"Grabarr /health returned {resp.status_code}: {resp.text[:200]}"
            )
        if resp.status_code != 200:
            raise DownloaderError(
                f"unexpected /health status {resp.status_code}: {resp.text[:200]}"
            )

        body = resp.json()
        protocol = body.get("protocol_version")
        if protocol != SUPPORTED_PROTOCOL_VERSION:
            raise VersionError(
                f"Grabarr protocol_version={protocol!r}, "
                f"this Romarr only speaks {SUPPORTED_PROTOCOL_VERSION}"
            )
        version = body.get("version") or "unknown"
        return str(version)

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        """Resolve ``source`` against Grabarr's ``/resolve`` and queue it.

        Only :class:`TorrentUrl` is supported on this branch — the
        URL must be the Torznab ``/download/{token}.torrent``
        enclosure the indexer search produced. Magnet / raw-bytes
        sources can't have come from a Grabarr indexer (the search
        path doesn't emit them), so they trip a ``ValueError`` here
        rather than silently ignoring.
        """
        if isinstance(source, TorrentMagnet):
            raise ValueError(
                "grabarr_direct expects a Torznab /download URL, "
                "not a magnet — check the indexer routing pin"
            )
        if isinstance(source, TorrentBytes):
            raise ValueError(
                "grabarr_direct expects a Torznab /download URL, "
                "not raw torrent bytes"
            )
        assert isinstance(source, TorrentUrl)

        slug, token = self._parse_torznab_url(str(source.url))
        resolve = await self._fetch_resolve(slug, token)

        native_id = f"grabarr-{token}"
        self._pending[native_id] = {
            "method": resolve["method"],
            "filename": resolve.get("filename"),
            "expected_size": resolve.get("expected_size"),
            "url": resolve.get("url"),
            "magnet_uri": resolve.get("magnet_uri"),
            "headers": resolve.get("headers") or {},
            "checksums": resolve.get("checksums") or {},
            "category": category,
            "tags": list(tags),
            "save_path": save_path,
            "added_at": datetime.now(UTC),
        }

        if resolve["method"] == "torrent_magnet":
            # R2d will re-route to the operator's qBit client via the
            # routing engine with SourceKind.TORRENT + a TorrentMagnet
            # source. For this slice we surface the gap loudly so a
            # test fixture that hits this branch can pin the contract.
            raise NotImplementedError(
                "magnet delegation lands in R2d — call routes through "
                "the linked qBit client instead of grabarr_direct"
            )

        if resolve["method"] != "http_direct":
            raise DownloaderError(
                f"unknown resolve method {resolve['method']!r} "
                "(check Grabarr protocol_version)"
            )

        _log.info(
            "grabarr_direct[%s]: resolved %s -> %s (%d bytes)",
            native_id,
            token,
            resolve.get("url"),
            resolve.get("expected_size") or -1,
        )
        # R2d streams the file with httpx + writes to disk + updates
        # progress here. This slice leaves the entry pending and lets
        # tests assert on the contract.
        return native_id

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        raise ValueError("grabarr_direct does not accept Usenet sources")

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        """Placeholder lifecycle reporter — R2d ships the real one.

        Returns a fixed ``QUEUED`` state with zero progress so the
        queue UI shows "queued" forever on entries this client added
        (since R2c does not actually run the download). ``available
        = False`` keeps the reconciler from polling rows of this
        type in production until R2d wires the real loop.
        """
        snap = self._pending.get(client_native_id)
        if snap is None:
            raise DownloaderError(f"unknown native_id {client_native_id!r}")
        return DownloadStatus(
            client_id=self.client_id,
            client_native_id=client_native_id,
            name=snap.get("filename") or client_native_id,
            state=DownloadState.QUEUED,
            progress=0.0,
            eta_seconds=None,
            seeders=None,
            peers=None,
            download_rate_bps=None,
            upload_rate_bps=None,
            total_bytes=snap.get("expected_size"),
            save_path=snap.get("save_path"),
            completed_paths=[],
            fetched_at=datetime.now(UTC),
        )

    async def remove(
        self, client_native_id: str, *, delete_files: bool
    ) -> None:
        # No files to delete in R2c — only the in-memory entry.
        self._pending.pop(client_native_id, None)

    async def set_imported_tag(self, client_native_id: str) -> None:
        # No client-side tag store; the queue table's own state is
        # the source of truth for "this grab was imported". No-op so
        # the importer's post-import hook stays uniform across clients.
        return None

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        # R2d returns completed http_direct entries here so the
        # importer's watcher can pick them up. R2c has none.
        return []

    async def ensure_category(self) -> None:
        # Grabarr-direct has no category concept of its own — the
        # category is carried on the in-memory pending entry only.
        return None

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _parse_torznab_url(url: str) -> tuple[str, str]:
        m = _TORZNAB_DOWNLOAD_RE.search(url)
        if not m:
            raise ValueError(
                f"URL does not look like a Grabarr Torznab download: {url!r}"
            )
        return m.group("slug"), m.group("token")

    async def _fetch_resolve(self, slug: str, token: str) -> dict[str, Any]:
        url = f"{self.base_url}/romarr/{slug}/api/v1/resolve/{token}"
        try:
            async with self._new_client() as client:
                resp = await client.get(url)
        except (httpx.HTTPError,) as exc:
            raise DownloaderConnError(f"resolve fetch failed: {exc}") from exc

        if resp.status_code == 401:
            raise AuthError(f"Grabarr rejected the apikey on /resolve ({url})")
        if resp.status_code == 403:
            raise AuthError(
                f"Grabarr returned 403 forbidden on /resolve ({url}) — "
                "token belongs to a different profile?"
            )
        if resp.status_code == 404:
            raise DownloaderError(
                f"Grabarr token expired or unknown ({url}) — "
                "re-run the search and try again"
            )
        if resp.status_code != 200:
            raise DownloaderError(
                f"unexpected /resolve status {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        return resp.json()


__all__ = ["GrabarrDirectClient", "SUPPORTED_PROTOCOL_VERSION"]
