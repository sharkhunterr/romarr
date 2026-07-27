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
import hashlib
import logging
import os
import re
import ssl
import zlib
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
    # Slice 427 / R3a — the wizard endpoint is the supported
    # creation path; ``available`` now matches reality. The Add
    # Download Client modal's ``_CLIENT_TYPES`` array stays at the
    # qBit/SAB/stubs set so the type is still hidden from the
    # generic add flow — the dedicated wizard route is the entry.
    available: ClassVar[bool] = True

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

    # The dispatcher must NOT resolve the URL for us — the whole point
    # of ``grabarr_direct`` is to hand Grabarr its own Torznab URL so
    # ``/resolve`` picks the transfer method (http_direct / magnet /
    # active_seed). See :attr:`DownloadClient.preserves_source_url`.
    preserves_source_url: ClassVar[bool] = True

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
            # Slice 439 — stash slug + token so ``_stream_to_disk``
            # can fire the ``grab-completed`` callback against
            # Grabarr's downloads page once the stream resolves.
            "slug": slug,
            "token": token,
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

        Slice 429 / R4 — when the resolve response carried per-file
        checksums (sha1 / md5 / crc32 — populated by Grabarr from
        ``SearchResult.metadata``), we compute the same digests
        incrementally during the stream and verify post-completion.
        A mismatch marks the entry FAILED with a
        ``checksum_mismatch`` error and unlinks the file so the
        importer never picks up a tampered or interrupted download.
        Checksums absent from the response → verification step is
        a no-op, file is trusted as-is.
        """
        snap = self._pending[native_id]
        url = snap["url"]
        headers = dict(snap.get("headers") or {})
        category = snap.get("category") or self._category
        filename = self._safe_filename(snap.get("filename") or native_id)
        # Slice 439 — extract slug + token from the original Torznab
        # download URL stashed during add_torrent so the
        # ``grab-completed`` callback below can locate the source
        # profile + token on Grabarr's side.
        callback_slug = snap.get("slug")
        callback_token = snap.get("token")
        explicit_save = snap.get("save_path")
        target_path = (
            Path(explicit_save)
            if explicit_save
            else self._download_root / category / filename
        )
        snap["state"] = "DOWNLOADING"
        snap["save_path"] = str(target_path)
        expected = snap.get("checksums") or {}
        # Hashers run incrementally on every chunk so the final
        # state ends up with the digest without a second pass over
        # the file. Lazily initialised only for digests we care
        # about (skip md5 if the resolve didn't include it).
        hashers = _build_hashers(expected)
        crc = 0 if "crc32" in expected else None
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(
                verify=self._verify, timeout=self._timeout, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code >= 400:
                        raise DownloaderError(
                            f"upstream {resp.status_code} fetching {url}"
                        )
                    # Slice 436 — reject HTML / text content delivered
                    # under a binary filename. Several sources (Axekin
                    # via vikingfile, Anna's Archive cascade landing on
                    # CF challenge, planet-emu under rate-limit, …)
                    # serve a 200 OK HTML page rather than a 4xx when
                    # the real download isn't available. Pre-slice the
                    # streamer wrote the HTML bytes verbatim and
                    # marked COMPLETED; the importer then choked with
                    # "Not a RAR file" / "bad zip" downstream. We
                    # bail loudly here with a message that points to
                    # the upstream-side issue.
                    content_type = (
                        (resp.headers.get("content-type") or "")
                        .split(";", 1)[0].strip().lower()
                    )
                    expected_binary = _looks_binary_extension(
                        target_path.suffix
                    )
                    if expected_binary and content_type.startswith("text/"):
                        raise DownloaderError(
                            f"upstream returned {content_type or 'unknown'} "
                            f"for a binary file ({target_path.name}); "
                            "likely a CF challenge / rate-limit / login "
                            "redirect — check the source's status"
                        )
                    total = (
                        int(resp.headers.get("content-length"))
                        if resp.headers.get("content-length")
                        else snap.get("expected_size") or 0
                    )
                    snap["total_bytes"] = total or snap.get("expected_size")
                    bytes_done = 0
                    first_chunk_sniff = True
                    with target_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if first_chunk_sniff and expected_binary:
                                # Slice 436 — magic-byte sniff on the
                                # very first chunk. Catches sources
                                # that ship ``Content-Type: application/
                                # octet-stream`` but the body is still
                                # HTML (some CF-protected hosts do
                                # this on a challenge response). Cheap
                                # — we only inspect the first 64 bytes
                                # once, then disable for the rest.
                                first_chunk_sniff = False
                                if _looks_like_html(chunk[:128]):
                                    raise DownloaderError(
                                        f"upstream returned HTML payload for "
                                        f"a binary file ({target_path.name}); "
                                        "first chunk: "
                                        f"{chunk[:60].decode('ascii', 'replace')!r}"
                                    )
                            fh.write(chunk)
                            bytes_done += len(chunk)
                            snap["bytes_done"] = bytes_done
                            snap["progress"] = (
                                bytes_done / total if total else 0.0
                            )
                            for h in hashers.values():
                                h.update(chunk)
                            if crc is not None:
                                crc = zlib.crc32(chunk, crc)

            # Post-stream checksum verification. Compare every digest
            # the resolver provided against what we just computed.
            # First mismatch wins — surface it loudly with the
            # expected vs actual side-by-side for the operator's
            # error rail.
            actual: dict[str, str] = {
                name: h.hexdigest() for name, h in hashers.items()
            }
            if crc is not None:
                actual["crc32"] = f"{crc & 0xFFFFFFFF:08x}"
            mismatches = _checksum_mismatches(expected, actual)
            if mismatches:
                raise DownloaderError(
                    "checksum_mismatch: "
                    + "; ".join(
                        f"{algo} expected={exp} actual={act}"
                        for algo, exp, act in mismatches
                    )
                )

            snap["state"] = "COMPLETED"
            snap["progress"] = 1.0 if snap.get("total_bytes") else 0.0
            snap["computed_checksums"] = actual
            _log.info(
                "grabarr_direct[%s]: completed %s (%d bytes, %d checksums verified)",
                native_id, target_path, bytes_done, len(mismatches) and 0 or len(expected),
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
            # Slice 439 — fire-and-forget callback so Grabarr's
            # downloads page reflects the http_direct grab. We
            # only care about the eventual visibility, so any
            # failure (Grabarr down, profile rotated apikey,
            # token already expired) is swallowed; the local
            # snap stays authoritative for Romarr's own queue.
            if callback_slug and callback_token:
                try:
                    await self._post_grab_completed(
                        slug=callback_slug,
                        token=callback_token,
                        success=snap["state"] == "COMPLETED",
                        size_bytes=snap.get("bytes_done"),
                        filename=snap.get("filename"),
                        error=snap.get("error"),
                        checksums=snap.get("computed_checksums") or {},
                    )
                except Exception as exc:  # noqa: BLE001 — telemetry only
                    _log.info(
                        "grabarr_direct[%s]: grab-completed callback failed (visibility only, "
                        "queue state already correct): %s",
                        native_id, exc,
                    )

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
            # Slice 438 — surface the streamer's recorded failure
            # ("checksum_mismatch", "upstream 404", "CF challenge")
            # so the queue_reconciler can write it to error_msg.
            error=snap.get("error"),
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

    async def _post_grab_completed(
        self,
        *,
        slug: str,
        token: str,
        success: bool,
        size_bytes: int | None,
        filename: str | None,
        error: str | None,
        checksums: dict[str, str],
    ) -> None:
        """Slice 439 — POST ``/grab-completed/{token}`` so Grabarr's
        downloads page surfaces the http_direct grab. Pre-slice
        the http_direct path bypassed Grabarr's Torznab
        ``/download/{token}.torrent`` route entirely; operators
        lost the visibility they had under the BitTorrent-wrap
        path. This callback rebuilds it without changing the
        bytes-on-disk topology (Romarr still owns the file)."""
        url = f"{self.base_url}/romarr/{slug}/api/v1/grab-completed/{token}"
        body: dict[str, Any] = {
            "success": success,
            "size_bytes": size_bytes,
            "filename": filename,
            "error": error,
            "sha1": checksums.get("sha1"),
            "md5": checksums.get("md5"),
            "crc32": checksums.get("crc32"),
        }
        # Strip None values so the pydantic body validator stays
        # strict on ``extra='forbid'`` without complaining about
        # nulls in optional fields.
        body = {k: v for k, v in body.items() if v is not None}
        async with self._new_client() as client:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                raise DownloaderError(
                    f"Grabarr /grab-completed returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )

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


# Slice 436 — extensions we treat as "definitely binary", refusing
# any HTML / text payload served under them. Cover the ROM / archive
# / disc-image surface. Anything outside this set falls back to the
# magic-byte sniff alone (a .nfo or .txt source legitimately served
# as text won't trip).
_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".rar", ".zip", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst",
    ".iso", ".bin", ".cue", ".chd", ".img", ".rvz", ".wbfs", ".wia",
    ".gba", ".gb", ".gbc", ".nds", ".3ds", ".cia",
    ".n64", ".z64", ".v64", ".smc", ".sfc", ".nes", ".smd", ".md", ".sms",
    ".pbp", ".cso", ".m3u",
    ".epub", ".pdf", ".mobi", ".azw3", ".djvu",
    ".mp3", ".flac", ".ogg", ".m4a", ".wav",
})


def _looks_binary_extension(suffix: str) -> bool:
    return suffix.lower() in _BINARY_EXTENSIONS


def _looks_like_html(head: bytes) -> bool:
    """Cheap test: does the first chunk look like HTML output?

    Catches the CF-challenge / rate-limit landing pages some
    upstream sources (Axekin via vikingfile, Anna's Archive on a
    bad mirror) return with a 200 OK status under any content-type.
    """
    stripped = head.lstrip()[:200].lower()
    return (
        stripped.startswith(b"<!doctype html")
        or stripped.startswith(b"<html")
        or stripped.startswith(b"<head")
        or b"<title>" in stripped
    )


def _build_hashers(
    expected: dict[str, str],
) -> dict[str, Any]:  # Any = hashlib._Hash (private type)
    """Initialise hashlib objects for every algorithm the resolver
    provided a digest for. Unknown algorithms are silently skipped
    — the protocol could introduce new ones (sha256 in v2) without
    requiring an old Romarr to update."""
    out: dict[str, Any] = {}
    for algo in ("sha1", "md5"):
        if algo in expected:
            out[algo] = hashlib.new(algo)
    return out


def _checksum_mismatches(
    expected: dict[str, str], actual: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Return ``(algo, expected, actual)`` for each digest where the
    streamer computed a value that doesn't match the resolver's
    reference. Comparison is case-insensitive (Edge Emulation
    returns lowercase, no-intro DATs are uppercase)."""
    out: list[tuple[str, str, str]] = []
    for algo, exp in expected.items():
        act = actual.get(algo)
        if act is None:
            # Algorithm advertised by the resolver but we didn't
            # compute it — covered by ``_build_hashers``'s allow-list.
            # Skipping rather than failing so a Romarr that doesn't
            # know about ``sha256`` doesn't block a download.
            continue
        if exp.lower() != act.lower():
            out.append((algo, exp, act))
    return out


__all__ = ["GrabarrDirectClient", "SUPPORTED_PROTOCOL_VERSION"]
