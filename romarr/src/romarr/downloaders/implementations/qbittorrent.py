"""qBittorrent download client.

Implementation note (deviation from FR-004): the spec mandates the
``qbittorrent-api`` Python library. We instead hit qBittorrent's
documented Web API v2 directly through ``httpx`` so:

  * the test surface stays uniform with SAB (single respx-based
    fixture set, no per-library mock plumbing);
  * the I/O stays async-native (``qbittorrent-api`` is sync and
    would force every call through ``asyncio.to_thread``, blocking
    a worker thread per call);
  * one less third-party dep to track.

The qBit Web API surface is stable across 4.x and well-documented
(``/api/v2/auth/login`` + ``/api/v2/app/*`` + ``/api/v2/torrents/*``),
so the trade-off is operationally low-risk.

CL001 (FR-004a) idempotency: when a magnet's info-hash is already
present, ``add_torrent`` returns the existing hash and additively
merges the ``romarr`` + ``romarr-{platform}`` tags via
``/api/v2/torrents/addTags``; the existing category is left intact.

CL003 (FR-005a) min-version gate: ``test_connection`` queries
``/api/v2/app/webapiVersion`` and rejects anything older than
``2.8.3`` (qBittorrent < 4.4.0) with :class:`VersionError`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    DownloaderError,
    TLSError,
    VersionError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.tags import TAG_IMPORTED, TAG_ROMARR
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

MIN_WEBAPI_VERSION = (2, 8, 3)
"""Minimum supported qBittorrent Web API version (qBit >= 4.4.0)."""

_INFO_HASH_RE = re.compile(r"xt=urn:btih:([0-9a-fA-F]{40}|[A-Z2-7]{32})")
"""Magnet info-hash extractor: SHA-1 hex (40) or base32 (32)."""


class QBittorrentClient(DownloadClient):
    """qBittorrent implementation of the download-client ABC."""

    client_type: ClassVar[ClientType] = ClientType.QBITTORRENT
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False

    def __init__(
        self,
        *,
        client_id: int,
        name: str,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = False,
        url_base: str | None = None,
        ssl_cert_validation: SslCertValidation = "enabled",
        category_default: str = TAG_ROMARR,
        timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(client_id=client_id, name=name)
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._scheme = "https" if use_ssl else "http"
        self._url_base = (url_base or "").rstrip("/")
        self._verify = build_httpx_verify(ssl_cert_validation, host)
        self._category = category_default
        self._timeout = timeout_seconds

    @property
    def base_url(self) -> str:
        """Fully-qualified ``/api/v2`` endpoint."""
        return f"{self._scheme}://{self._host}:{self._port}{self._url_base}/api/v2"

    # ---- HTTP plumbing --------------------------------------------------------

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(verify=self._verify, timeout=self._timeout)

    async def _login(self, client: httpx.AsyncClient) -> None:
        """POST credentials and let httpx pick up the SID cookie.

        qBit's Web API quirk: bad credentials return HTTP 200 with body
        ``Fails.``; 403 is reserved for IP-based bans. We translate
        either to :class:`AuthError`.
        """
        try:
            response = await client.post(
                f"{self.base_url}/auth/login",
                data={"username": self._username, "password": self._password},
                headers={"Referer": self._origin},
            )
        except httpx.ConnectError as exc:
            if "ssl" in str(exc).lower() or "certificate" in str(exc).lower():
                raise TLSError(f"qBittorrent TLS handshake failed: {exc}") from exc
            raise DownloaderConnError(
                f"qBittorrent unreachable: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise DownloaderConnError(f"qBittorrent timed out: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthError(
                f"qBittorrent rejected login: HTTP {response.status_code}"
            )
        body = response.text.strip().lower()
        if body and body != "ok.":
            raise AuthError(f"qBittorrent rejected login: {response.text!r}")
        if "SID" not in client.cookies:
            raise AuthError("qBittorrent did not return an SID cookie")

    @property
    def _origin(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}"

    async def _get(
        self, client: httpx.AsyncClient, path: str, **params: str
    ) -> httpx.Response:
        return await self._send(client, "GET", path, params=params)

    async def _post(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> httpx.Response:
        return await self._send(client, "POST", path, data=data, files=files)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            response = await client.request(
                method,
                url,
                params=params,
                data=data,
                files=files,
                headers={"Referer": self._origin},
            )
        except httpx.TimeoutException as exc:
            raise DownloaderConnError(f"qBittorrent timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            if "ssl" in str(exc).lower() or "certificate" in str(exc).lower():
                raise TLSError(f"qBittorrent TLS handshake failed: {exc}") from exc
            raise DownloaderConnError(
                f"qBittorrent unreachable: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise AuthError(
                f"qBittorrent rejected request: HTTP {response.status_code}"
            )
        if response.status_code >= 500:
            raise DownloaderConnError(
                f"qBittorrent server error: HTTP {response.status_code}"
            )
        return response

    # ---- ABC contract ---------------------------------------------------------

    async def test_connection(self) -> str:
        async with self._new_client() as client:
            await self._login(client)
            webapi_response = await self._get(client, "/app/webapiVersion")
            webapi = webapi_response.text.strip()
            _enforce_min_webapi_version(webapi)

            version_response = await self._get(client, "/app/version")
            return f"qBittorrent {version_response.text.strip()}"

    async def ensure_category(self) -> None:
        async with self._new_client() as client:
            await self._login(client)
            cats_response = await self._get(client, "/torrents/categories")
            try:
                categories = cats_response.json()
            except ValueError as exc:
                raise DownloaderError(
                    "qBittorrent categories response was not JSON"
                ) from exc
            if self._category in categories:
                return
            create = await self._post(
                client,
                "/torrents/createCategory",
                data={"category": self._category, "savePath": ""},
            )
            if create.status_code >= 400:
                raise CategoryWarning(
                    f"qBittorrent could not create category {self._category!r}: "
                    f"HTTP {create.status_code}"
                )

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        async with self._new_client() as client:
            await self._login(client)

            # Pre-resolve indexer-proxied URLs. Prowlarr (and a
            # few private trackers) reply 301 with
            # ``Location: magnet:?xt=…`` to the
            # ``/<id>/download?apikey=…`` endpoint. Handing that
            # raw URL to qBit's ``/torrents/add`` succeeds at the
            # HTTP level but qBit can't follow ``magnet:`` from
            # an HTTP redirect — the torrent never registers and
            # the add silently no-ops, which used to surface as
            # ``did not surface the just-added torrent`` from the
            # post-add discovery step. We follow the redirect
            # ourselves and substitute the resolved source so
            # qBit gets a vocabulary it understands (a magnet URI
            # or the .torrent bytes).
            if isinstance(source, TorrentUrl):
                resolved = await self._resolve_torrent_url(str(source.url))
                if resolved is not None:
                    source = resolved

            magnet_hash = _maybe_extract_magnet_hash(source)
            if magnet_hash:
                existing = await self._fetch_torrent_by_hash(client, magnet_hash)
                if existing is not None:
                    # CL001 / FR-004a: idempotent — merge tags additively,
                    # leave existing category alone, return existing hash.
                    if tags:
                        await self._post(
                            client,
                            "/torrents/addTags",
                            data={
                                "hashes": magnet_hash.lower(),
                                "tags": ",".join(tags),
                            },
                        )
                    return magnet_hash.lower()

            await self._submit_torrent(
                client,
                source,
                category=category,
                tags=tags,
                save_path=save_path,
            )
            if magnet_hash:
                return magnet_hash.lower()
            return await self._discover_added_hash(client, source)

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        raise NotImplementedError("qBittorrent does not handle NZB sources")

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        async with self._new_client() as client:
            await self._login(client)
            data = await self._fetch_torrent_by_hash(client, client_native_id)
            if data is None:
                raise DownloaderError(
                    f"qBittorrent has no torrent with hash {client_native_id!r}"
                )

            files_response = await self._get(
                client, "/torrents/files", hash=client_native_id.lower()
            )
            try:
                files = files_response.json()
            except ValueError:
                files = []

            return _build_status(
                self.client_id, data, files=files, fetched_at=datetime.now(UTC)
            )

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        """List romarr-managed torrents whose download has finished.

        Filters: ``category == TAG_ROMARR``, state is one of the
        completed/seeding states (per ``_QBIT_COMPLETED_STATES``).
        Items already carrying the ``romarr-imported`` tag are
        flagged ``imported=True`` rather than skipped — the watcher
        loop's dedup uses the flag.
        """
        async with self._new_client() as client:
            await self._login(client)
            response = await self._get(
                client, "/torrents/info", category=self._category
            )
            try:
                payload = response.json()
            except ValueError:
                return []

        out: list[ManagedDownload] = []
        if not isinstance(payload, list):
            return out

        for entry in payload:
            if not isinstance(entry, dict):
                continue
            state = str(entry.get("state") or "")
            if state not in _QBIT_COMPLETED_STATES:
                continue
            tags_raw = str(entry.get("tags") or "")
            tag_set = {t.strip() for t in tags_raw.split(",") if t.strip()}
            native_id = str(entry.get("hash") or "")
            if not native_id:
                continue
            out.append(
                ManagedDownload(
                    client_id=self.client_id,
                    client_native_id=native_id,
                    name=str(entry.get("name") or native_id),
                    save_path=str(
                        entry.get("content_path")
                        or entry.get("save_path")
                        or ""
                    ),
                    imported=TAG_IMPORTED in tag_set,
                )
            )
        return out

    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        async with self._new_client() as client:
            await self._login(client)
            await self._post(
                client,
                "/torrents/delete",
                data={
                    "hashes": client_native_id.lower(),
                    "deleteFiles": "true" if delete_files else "false",
                },
            )

    async def set_imported_tag(self, client_native_id: str) -> None:
        """Add the ``romarr-imported`` tag (FR-013).

        Uses qBit's ``/torrents/addTags`` which is additive — existing
        ``romarr`` / ``romarr-{platform}`` tags survive untouched.
        """
        async with self._new_client() as client:
            await self._login(client)
            await self._post(
                client,
                "/torrents/addTags",
                data={
                    "hashes": client_native_id.lower(),
                    "tags": TAG_IMPORTED,
                },
            )

    # ---- internals ------------------------------------------------------------

    async def _fetch_torrent_by_hash(
        self, client: httpx.AsyncClient, info_hash: str
    ) -> dict[str, Any] | None:
        response = await self._get(
            client, "/torrents/info", hashes=info_hash.lower()
        )
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, list) or not payload:
            return None
        return payload[0] if isinstance(payload[0], dict) else None

    async def _submit_torrent(
        self,
        client: httpx.AsyncClient,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None,
    ) -> None:
        data: dict[str, str] = {
            "category": category,
            "tags": ",".join(tags),
        }
        if save_path:
            data["savepath"] = save_path

        files: dict[str, tuple[str, bytes, str]] | None = None
        if isinstance(source, TorrentMagnet):
            data["urls"] = source.magnet_uri
        elif isinstance(source, TorrentUrl):
            data["urls"] = str(source.url)
        elif isinstance(source, TorrentBytes):
            files = {
                "torrents": ("upload.torrent", source.data, "application/x-bittorrent")
            }
        else:  # pragma: no cover — guarded by discriminated union
            raise TypeError(f"unsupported TorrentSource: {type(source)!r}")

        await self._post(client, "/torrents/add", data=data, files=files)

    async def _resolve_torrent_url(
        self, url: str
    ) -> TorrentSource | None:
        """Follow one redirect manually so we can swap a
        ``magnet:`` Location for a ``TorrentMagnet`` source.

        Returns:
            * ``TorrentMagnet`` when the indexer 30x's to ``magnet:?xt=…``
              (Prowlarr's torrent-private fallback);
            * ``TorrentBytes`` when the indexer serves a 200 with a
              ``.torrent`` payload directly;
            * ``None`` when the URL is plain HTTP and qBit can
              fetch it itself (the original behaviour).
        """
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                verify=self._verify,
                follow_redirects=False,
            ) as probe:
                response = await probe.get(url)
        except httpx.HTTPError:
            return None

        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if location.startswith("magnet:"):
                return TorrentMagnet(magnet_uri=location)
            # HTTP→HTTP redirect → let qBit follow it itself.
            return None

        if response.status_code == 200:
            content_type = (
                response.headers.get("content-type", "").lower()
            )
            body = response.content
            looks_like_torrent = (
                "application/x-bittorrent" in content_type
                or content_type.startswith("application/octet-stream")
                # Bencoded torrent files start with ``d`` followed
                # by a length-prefixed key — use the canonical
                # ``announce`` / ``info`` first key as a sniff.
                or body.startswith(b"d8:announce")
                or body.startswith(b"d4:info")
            )
            if looks_like_torrent and body:
                return TorrentBytes(data=body)

        return None

    async def _discover_added_hash(
        self, client: httpx.AsyncClient, source: TorrentSource
    ) -> str:
        """Find the just-added torrent by listing the category.

        qBit's ``/torrents/add`` doesn't return the new hash, so we
        list the category and pick the most recent. This is best-effort
        — if the operator manually added another torrent in the same
        category in the same second, the result is non-deterministic;
        magnet sources avoid this entirely via :func:`_INFO_HASH_RE`.
        """
        del source  # intentionally unused; surface mirrors a future signature
        response = await self._get(
            client,
            "/torrents/info",
            category=self._category,
            sort="added_on",
            reverse="true",
            limit="1",
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DownloaderError(
                "qBittorrent /torrents/info returned non-JSON"
            ) from exc
        if not isinstance(payload, list) or not payload:
            raise DownloaderError(
                "qBittorrent did not surface the just-added torrent"
            )
        return str(payload[0].get("hash", "")).lower()


# ---------------------------------------------------------------------------
# Version gate (CL003 / FR-005a)
# ---------------------------------------------------------------------------


def _enforce_min_webapi_version(webapi: str) -> None:
    parsed = _parse_version(webapi)
    if parsed is None:
        raise VersionError(
            f"qBittorrent returned an unparseable webapiVersion: {webapi!r}"
        )
    if parsed < MIN_WEBAPI_VERSION:
        raise VersionError(
            f"qBittorrent webapiVersion {webapi} is below the minimum "
            f"{'.'.join(str(p) for p in MIN_WEBAPI_VERSION)} — "
            f"upgrade qBittorrent to 4.4.0 or newer"
        )


def _parse_version(raw: str) -> tuple[int, ...] | None:
    parts = raw.strip().lstrip("v").split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Magnet info-hash extraction
# ---------------------------------------------------------------------------


def _maybe_extract_magnet_hash(source: TorrentSource) -> str | None:
    """Return the SHA-1 info-hash (40 hex chars) for a magnet, else None.

    Base32 hashes are uppercased into the 32-char form; qBit normalizes
    those internally on add, but for the lookup we hand qBit the
    canonical hex form when we have it. For base32 magnets we skip the
    pre-check (the post-add list-and-pick path handles them).
    """
    if not isinstance(source, TorrentMagnet):
        return None
    match = _INFO_HASH_RE.search(source.magnet_uri)
    if not match:
        return None
    raw = match.group(1)
    if len(raw) == 40:
        return raw.lower()
    # Base32 — skip the pre-check; let qBit handle dedup internally.
    return None


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


_QBIT_COMPLETED_STATES: frozenset[str] = frozenset(
    {
        "uploading",
        "stalledUP",
        "forcedUP",
        "pausedUP",
        "stoppedUP",
        "checkingUP",
        "queuedUP",
    }
)
"""qBit native states meaning "the download is finished and on disk".

The torrent may be seeding, paused, or queued in the upload phase —
all four mean the importer can pick it up. Active-download / queued-
download states are excluded so we don't grab in-flight files.
"""


_STATE_MAP: dict[str, DownloadState] = {
    "allocating": DownloadState.QUEUED,
    "queuedDL": DownloadState.QUEUED,
    "queuedUP": DownloadState.QUEUED,
    "metaDL": DownloadState.DOWNLOADING,
    "downloading": DownloadState.DOWNLOADING,
    "forcedDL": DownloadState.DOWNLOADING,
    "stalledDL": DownloadState.STALLED,
    "checkingDL": DownloadState.DOWNLOADING,
    "checkingUP": DownloadState.SEEDING,
    "checkingResumeData": DownloadState.QUEUED,
    "uploading": DownloadState.SEEDING,
    "stalledUP": DownloadState.SEEDING,
    "forcedUP": DownloadState.SEEDING,
    "pausedDL": DownloadState.PAUSED,
    "pausedUP": DownloadState.COMPLETED,
    "stoppedDL": DownloadState.PAUSED,
    "stoppedUP": DownloadState.COMPLETED,
    "missingFiles": DownloadState.FAILED,
    "error": DownloadState.FAILED,
    "moving": DownloadState.DOWNLOADING,
    "unknown": DownloadState.QUEUED,
}


def _build_status(
    client_id: int,
    payload: dict[str, Any],
    *,
    files: list[dict[str, Any]],
    fetched_at: datetime,
) -> DownloadStatus:
    raw_state = str(payload.get("state", "unknown"))
    state = _STATE_MAP.get(raw_state, DownloadState.QUEUED)

    progress_value = payload.get("progress")
    progress = float(progress_value) if isinstance(progress_value, int | float) else 0.0
    progress = max(0.0, min(1.0, progress))

    eta_value = payload.get("eta")
    # qBit reports 8640000 (~100 days) for "unknown" — collapse to None.
    eta_seconds: int | None = (
        eta_value
        if isinstance(eta_value, int) and 0 < eta_value < 8_000_000
        else None
    )

    save_path_value = payload.get("save_path")
    save_path = save_path_value if isinstance(save_path_value, str) and save_path_value else None

    completed_paths: list[str] = []
    if state in (DownloadState.COMPLETED, DownloadState.SEEDING) and save_path:
        for entry in files:
            name = entry.get("name")
            file_progress = entry.get("progress", 0)
            if (
                isinstance(name, str)
                and isinstance(file_progress, int | float)
                and file_progress >= 1.0
            ):
                completed_paths.append(f"{save_path.rstrip('/')}/{name}")

    # qBit's /torrents/info exposes ``size`` (selected-files
    # byte count) and ``total_size`` (full torrent). Prefer
    # ``size`` since that's what the operator chose to download;
    # fall back to ``total_size`` so we never end up at 0.
    total_bytes = (
        _coerce_int(payload.get("size"))
        or _coerce_int(payload.get("total_size"))
    )
    return DownloadStatus(
        client_id=client_id,
        client_native_id=str(payload.get("hash", "")).lower(),
        name=str(payload.get("name", "")),
        state=state,
        progress=progress,
        eta_seconds=eta_seconds,
        seeders=_coerce_int(payload.get("num_seeds")),
        peers=_coerce_int(payload.get("num_leechs")),
        download_rate_bps=_coerce_int(payload.get("dlspeed")),
        upload_rate_bps=_coerce_int(payload.get("upspeed")),
        total_bytes=total_bytes,
        save_path=save_path,
        completed_paths=completed_paths,
        fetched_at=fetched_at,
    )


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


__all__ = ["MIN_WEBAPI_VERSION", "QBittorrentClient"]
