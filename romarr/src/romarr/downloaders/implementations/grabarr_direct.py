"""Grabarr-direct client — slice 425 http_direct streaming.

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

   - ``http_direct``    — spawn a background asyncio task that
     httpx-streams the upstream URL to disk under
     ``{download_root}/{category}/{filename}``. Progress is
     tracked in an in-memory dict ``get_status`` reads from.
     This is the path that **kills the BitTorrent-wrap detour
     for HTTP-direct sources** (Internet Archive, RomsFun,
     Edge Emulation, …) — Romarr pulls the bytes itself, no
     qBit, no DHT, no Grabarr-side webseed proxy.
   - ``torrent_magnet`` — raises :class:`NotImplementedError`.
     **R2e** wires the magnet delegation: dispatcher pre-resolves
     for grabarr indexers and re-routes the magnet to the
     operator's qBit row via the routing engine.

Keeps ``available = False`` so the Add Download Client modal does
not surface this type yet — the "Add Grabarr" wizard (R3) is the
only intended creation path. Operators wiring rows directly via
the API today get a fully working http_direct downloader plus the
explicit magnet-deferred error.

See ``docs/grabarr-direct-protocol.md`` (v0.2.1) for the full
contract.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path
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
        download_root: str | Path | None = None,
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
        # Where the http_direct streamer writes files. The R3 wizard
        # slice will surface this as a column on the download_client
        # row; until then operators can pin it via the
        # ``ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT`` env var, and tests
        # inject ``tmp_path`` directly through the constructor.
        if download_root is None:
            download_root = os.environ.get(
                "ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT", "/downloads"
            )
        self._download_root = Path(download_root)
        # native_id -> snapshot dict tracking the in-flight or
        # completed transfer. Keys are stable; values mutate as the
        # streamer makes progress (``state``, ``bytes_done``,
        # ``progress``, ``save_path``, ``error``).
        self._pending: dict[str, dict[str, Any]] = {}
        # native_id -> asyncio.Task. Lets ``remove`` cancel an
        # in-flight transfer (and tests await completion via the
        # ``wait_for_task`` helper).
        self._tasks: dict[str, asyncio.Task[None]] = {}

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
        """Resolve ``source`` against Grabarr's ``/resolve`` and start
        the actual transfer.

        Only :class:`TorrentUrl` is supported — the URL must be the
        Torznab ``/download/{token}.torrent`` enclosure the indexer
        search produced. Magnet / raw-bytes sources can't have come
        from a Grabarr indexer (the search path doesn't emit them),
        so they trip a ``ValueError`` rather than silently ignoring.

        Returns immediately after the ``/resolve`` round-trip. For
        ``http_direct`` the actual byte-pull happens in a background
        ``asyncio.Task`` Romarr's reconciler observes via
        :meth:`get_status` (no blocking RPC on the search path).
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
        snap: dict[str, Any] = {
            "method": resolve["method"],
            "filename": resolve.get("filename"),
            "expected_size": resolve.get("expected_size"),
            "total_bytes": resolve.get("expected_size"),
            "url": resolve.get("url"),
            "magnet_uri": resolve.get("magnet_uri"),
            "headers": resolve.get("headers") or {},
            "checksums": resolve.get("checksums") or {},
            "category": category,
            "tags": list(tags),
            "save_path": save_path,
            "bytes_done": 0,
            "progress": 0.0,
            "state": "QUEUED",
            "error": None,
            "added_at": datetime.now(UTC),
        }
        self._pending[native_id] = snap

        if resolve["method"] == "torrent_magnet":
            # Slice 426 / R2e — the dispatcher's
            # ``maybe_pre_resolve`` in
            # :mod:`romarr.search.dispatch_grabarr` catches
            # torrent_magnet results BEFORE routing and re-routes
            # them to the operator's qBit row, filtering
            # grabarr_direct out of the candidate pool. If this
            # branch fires, the operator's qBit + Grabarr config
            # are out of sync — surface the gap loudly.
            raise DownloaderError(
                "grabarr_direct received a torrent_magnet resolve at "
                "add_torrent — the dispatcher's pre-resolve should "
                "have re-routed this to the operator's qBit client. "
                "Check that a qBittorrent download client is "
                "configured and enabled for torrents."
            )

        if resolve["method"] != "http_direct":
            raise DownloaderError(
                f"unknown resolve method {resolve['method']!r} "
                "(check Grabarr protocol_version)"
            )

        _log.info(
            "grabarr_direct[%s]: resolved %s -> %s (%d bytes), starting stream",
            native_id,
            token,
            resolve.get("url"),
            resolve.get("expected_size") or -1,
        )
        task = asyncio.create_task(self._stream_to_disk(native_id))
        self._tasks[native_id] = task
        # Yield once so the task gets scheduled before we return —
        # callers that hit get_status immediately see DOWNLOADING
        # rather than QUEUED (cosmetic, but avoids a confusing
        # race in the queue-page reconciler).
        await asyncio.sleep(0)
        return native_id

    # ---- streaming ----------------------------------------------------------

    async def _stream_to_disk(self, native_id: str) -> None:
        """Background task: stream the resolved URL to disk.

        Updates ``self._pending[native_id]`` as it goes. Catches
        every recoverable error and marks the entry FAILED with the
        message preserved — the reconciler relies on ``state +
        error`` to drive the queue-row UI rather than introspecting
        the task itself.
        """
        snap = self._pending[native_id]
        url = snap["url"]
        headers = dict(snap.get("headers") or {})
        category = snap.get("category") or self._category
        filename = self._safe_filename(snap.get("filename") or native_id)
        explicit_save = snap.get("save_path")
        target_path = (
            Path(explicit_save)
            if explicit_save
            else self._download_root / category / filename
        )
        snap["state"] = "DOWNLOADING"
        snap["save_path"] = str(target_path)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(
                verify=self._verify, timeout=self._timeout
            ) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code >= 400:
                        raise DownloaderError(
                            f"upstream {resp.status_code} fetching {url}"
                        )
                    total = (
                        int(resp.headers.get("content-length"))
                        if resp.headers.get("content-length")
                        else snap.get("expected_size") or 0
                    )
                    snap["total_bytes"] = total or snap.get("expected_size")
                    bytes_done = 0
                    with target_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
                            bytes_done += len(chunk)
                            snap["bytes_done"] = bytes_done
                            snap["progress"] = (
                                bytes_done / total if total else 0.0
                            )
            snap["state"] = "COMPLETED"
            snap["progress"] = 1.0 if snap.get("total_bytes") else 0.0
            _log.info(
                "grabarr_direct[%s]: completed %s (%d bytes)",
                native_id, target_path, bytes_done,
            )
        except asyncio.CancelledError:
            # Reraise so the task ends cancelled; ``remove`` already
            # popped the snapshot or marked it FAILED via finally.
            snap["state"] = "FAILED"
            snap["error"] = "cancelled"
            self._unlink_silently(target_path)
            raise
        except Exception as exc:  # noqa: BLE001 — surface as queue-row error
            snap["state"] = "FAILED"
            snap["error"] = str(exc)[:500]
            _log.warning(
                "grabarr_direct[%s]: stream failed: %s", native_id, exc
            )
            self._unlink_silently(target_path)
        finally:
            # The task list is informational. Pop here so callers
            # checking ``done()`` after completion don't see stale
            # entries.
            self._tasks.pop(native_id, None)

    @staticmethod
    def _safe_filename(name: str) -> str:
        # Reject path separators / parent-traversal segments. The
        # filename comes from Grabarr's adapter metadata; an
        # untrusted upstream shouldn't be able to write outside
        # ``download_root``.
        safe = Path(name).name or "file"
        if safe in (".", ".."):
            return "file"
        return safe

    @staticmethod
    def _unlink_silently(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    async def wait_for_task(self, native_id: str) -> None:
        """Test helper: await the background task for ``native_id``.

        No-op when the task already completed (and was popped from
        the registry). Production code does not use this — the
        reconciler reads ``get_status`` snapshots instead.
        """
        task = self._tasks.get(native_id)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                # Errors are already captured in self._pending[…].error.
                pass

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        raise ValueError("grabarr_direct does not accept Usenet sources")

    # Maps our internal string ``state`` (set by ``_stream_to_disk``)
    # to the canonical Romarr-side :class:`DownloadState` literal.
    # The strings are kept private to the snapshot dict — only this
    # mapping leaks out via :meth:`get_status`.
    _STATE_MAP: ClassVar[dict[str, DownloadState]] = {
        "QUEUED": DownloadState.QUEUED,
        "DOWNLOADING": DownloadState.DOWNLOADING,
        "COMPLETED": DownloadState.COMPLETED,
        "FAILED": DownloadState.FAILED,
    }

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        snap = self._pending.get(client_native_id)
        if snap is None:
            raise DownloaderError(f"unknown native_id {client_native_id!r}")
        state = self._STATE_MAP.get(snap["state"], DownloadState.STALLED)
        completed = (
            [snap["save_path"]]
            if state is DownloadState.COMPLETED and snap.get("save_path")
            else []
        )
        return DownloadStatus(
            client_id=self.client_id,
            client_native_id=client_native_id,
            name=snap.get("filename") or client_native_id,
            state=state,
            progress=float(snap.get("progress") or 0.0),
            eta_seconds=None,
            seeders=None,
            peers=None,
            download_rate_bps=None,
            upload_rate_bps=None,
            total_bytes=snap.get("total_bytes"),
            save_path=snap.get("save_path"),
            completed_paths=completed,
            fetched_at=datetime.now(UTC),
        )

    async def remove(
        self, client_native_id: str, *, delete_files: bool
    ) -> None:
        task = self._tasks.pop(client_native_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        snap = self._pending.pop(client_native_id, None)
        if snap is None:
            return
        if delete_files:
            path = snap.get("save_path")
            if path:
                self._unlink_silently(Path(path))

    async def set_imported_tag(self, client_native_id: str) -> None:
        # No client-side tag store; the queue table's own state is
        # the source of truth for "this grab was imported". No-op so
        # the importer's post-import hook stays uniform across
        # clients (callers fire-and-forget).
        return None

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        # The importer's watcher polls this to find files ready to
        # ingest. We surface every completed http_direct entry that
        # still has a save_path on disk — the watcher tags them
        # ``imported=False`` via its own dedup mechanism, since this
        # client carries no per-job tag store.
        out: list[ManagedDownload] = []
        for nid, snap in self._pending.items():
            if snap.get("state") != "COMPLETED":
                continue
            save_path = snap.get("save_path")
            if not save_path:
                continue
            out.append(
                ManagedDownload(
                    client_id=self.client_id,
                    client_native_id=nid,
                    name=snap.get("filename") or nid,
                    save_path=save_path,
                    imported=False,
                )
            )
        return out

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
