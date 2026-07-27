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

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

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

# Slice 416 — token helpers for meta-torrent file selection.
# Match the orchestrator's slice-415 walker so a file qBit
# picks at grab time is the same file the importer walks at
# import time.
_PATH_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PATH_STOPWORDS: frozenset[str] = frozenset(
    {"the", "of", "a", "an", "and", "in", "on", "no", "intro",
     "rom", "roms", "usa", "europe", "japan", "rev", "rerelease",
     "nintendo", "sega", "sony", "atari"}
)


def _significant_path_tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens minus noise + ubiquitous
    manufacturer words. A file living under
    ``No-Intro/Nintendo - Game Boy Advance/`` shouldn't score
    against an ``N64 / Nintendo 64`` platform purely on
    ``nintendo`` — drop manufacturer names so the title /
    platform-name signal dominates."""
    return {
        t
        for t in _PATH_TOKEN_RE.findall(text.lower())
        if len(t) >= 2 and t not in _PATH_STOPWORDS
    }
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
        # Session cookie detection. qBit's cookie name changed with 5.x:
        #   * qBit ≤ 4.x → ``SID``
        #   * qBit 5.x  → ``QBT_SID_<internal-port>`` (e.g.
        #     ``QBT_SID_8080``); the port encoded is qBit's internal
        #     listen port, NOT the port Romarr talks to (Docker port
        #     mapping is invisible to qBit).
        # We accept ANY cookie whose name starts with ``SID`` or
        # ``QBT_SID``. When no session cookie is present, probe
        # ``/api/v2/app/version`` to tell apart "subnet-bypass /
        # cookieless-but-authed" from "creds are wrong".
        has_session_cookie = any(
            name.upper().startswith(("SID", "QBT_SID"))
            for name in client.cookies.keys()
        )
        if not has_session_cookie:
            probe = await client.get(
                f"{self.base_url}/app/version",
                headers={"Referer": self._origin},
            )
            if probe.status_code in (401, 403):
                raise AuthError(
                    "qBittorrent rejected login (no session cookie and "
                    f"probe returned HTTP {probe.status_code})"
                )
            if probe.status_code >= 400:
                raise AuthError(
                    "qBittorrent probe after cookieless login failed: "
                    f"HTTP {probe.status_code}"
                )
            # 2xx probe → treat as authenticated (subnet-bypass case).

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
                    # Slice 405 — meta-torrent re-grab (Minerva /
                    # Erista archives surface many "individual"
                    # results that all share the same big info-
                    # hash). When this torrent was already tagged
                    # ``romarr-imported`` from a prior grab, the
                    # watcher would skip it and the new
                    # queue_entry would freeze forever. Strip the
                    # tag so the watcher re-processes the meta-
                    # torrent with the fresh queue_entry's
                    # pre_matched_game_id pointing at the new
                    # game.
                    existing_tags = {
                        t.strip()
                        for t in str(existing.get("tags") or "").split(",")
                        if t.strip()
                    }
                    if TAG_IMPORTED in existing_tags:
                        await self._post(
                            client,
                            "/torrents/removeTags",
                            data={
                                "hashes": magnet_hash.lower(),
                                "tags": TAG_IMPORTED,
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
            # qBit's ``hash`` field is the info-hash. Force
            # lowercase so it always matches what
            # ``_discover_added_hash`` / ``add_torrent`` persist
            # on ``queue_entry.download_client_native_id``;
            # without this normalisation the dispatcher's
            # native-id lookup misses (slice 373).
            native_id = str(entry.get("hash") or "").lower()
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

    async def select_only_matching_file(
        self,
        client_native_id: str,
        *,
        title_tokens: set[str],
        platform_tokens: set[str] | None = None,
        allowed_extensions: frozenset[str] | None = None,
        target_path: str | None = None,
    ) -> str | None:
        """Slice 416 — narrow a meta-torrent to one file via qBit's
        ``/torrents/filePrio`` API.

        For multi-file torrents (Minerva_Myrient, Erista archives,
        …), the indexer's "grab this game" result points at a
        specific file inside a giant shared torrent. Without
        intervention qBit picks files based on swarm availability
        and the operator often ends up with the wrong ROM
        downloaded. We score every file in the torrent by token
        overlap against the matched game's title + platform,
        priority-zero everything else, and priority-1 the
        winning file so qBit only fetches what the operator
        asked for.

        Single-file torrents are a no-op. Returns the matched
        file's path inside the torrent on success, ``None`` when
        no candidate clears the title-overlap floor.
        """
        platform_tokens = platform_tokens or set()
        async with self._new_client() as client:
            await self._login(client)
            # Slice 417 — a freshly-added magnet has no metadata
            # yet (qBit fetches the file list from the DHT, takes
            # a few seconds). If we read ``/torrents/files``
            # before that, qBit returns an empty list and we
            # short-circuit without setting any priority, so qBit
            # quietly downloads the WHOLE archive (Minerva is
            # 7.6 TB — never completes, never imports). Poll
            # ``has_metadata`` first.
            if not await self._wait_for_metadata(
                client, client_native_id.lower()
            ):
                logger.warning(
                    "qbit.select_only_matching_file.metadata_timeout "
                    "native_id=%s",
                    client_native_id,
                )
                return None
            response = await self._get(
                client, "/torrents/files", hash=client_native_id.lower()
            )
            try:
                files = response.json()
            except ValueError:
                return None
            if not isinstance(files, list) or len(files) <= 1:
                # Single-file torrent or unparseable — nothing
                # to narrow.
                return None

            # Slice 442 — when the caller provided an explicit
            # ``target_path`` (Grabarr's ``internal_file_path``
            # from /resolve, identifying the exact file the
            # operator picked from the search result), short-
            # circuit the token-overlap scoring and select that
            # file directly. Pre-slice the scoring could land on
            # a different release sharing parent-dir tokens
            # (user's Crash 3 (Europe) .zip grab losing to a USA
            # Demo .chd in the same Minerva meta-torrent).
            #
            # Path normalisation: Minerva ships paths like
            # ``./No-Intro/.../file.zip``; qBit prefixes every
            # entry with the torrent name (``Minerva_Myrient/No-
            # Intro/.../file.zip``). Compare on the lowercase
            # suffix — qBit's name should END with the
            # ``.``-stripped target_path. This handles both the
            # torrent-name prefix AND the leading-``./`` quirk
            # without needing to know either side's exact format.
            if target_path is not None:
                stripped_target = target_path.lstrip("./").lower()
                exact_idx: int | None = None
                for idx, entry in enumerate(files):
                    if not isinstance(entry, dict):
                        continue
                    name = str(entry.get("name") or "")
                    if not name:
                        continue
                    if name.lower().endswith(stripped_target):
                        exact_idx = idx
                        break
                if exact_idx is not None:
                    all_ids = "|".join(str(i) for i in range(len(files)))
                    if all_ids:
                        await self._post(
                            client,
                            "/torrents/filePrio",
                            hash=client_native_id.lower(),
                            id=all_ids,
                            priority="0",
                        )
                    await self._post(
                        client,
                        "/torrents/filePrio",
                        hash=client_native_id.lower(),
                        id=str(exact_idx),
                        priority="1",
                    )
                    logger.info(
                        "qbit.select_only_matching_file.target_path_match "
                        "native_id=%s idx=%d path=%s",
                        client_native_id,
                        exact_idx,
                        target_path,
                    )
                    return str(files[exact_idx].get("name") or target_path)
                # ``target_path`` was supposed to match but the
                # qBit-side metadata doesn't carry that path —
                # fall through to the token-overlap scoring as
                # a defensive fallback instead of refusing
                # outright.
                logger.warning(
                    "qbit.select_only_matching_file.target_path_miss "
                    "native_id=%s target=%s candidate_count=%d",
                    client_native_id,
                    target_path,
                    len(files),
                )

            # Slice 418 — two-pass selection so a meta-torrent
            # never picks a wrong-platform file. Minerva bundles
            # 46 000+ ROMs across every platform; an N64
            # ``GoldenEye 007`` grab against an archive that
            # only ships the DS apfix versions used to match
            # the DS file (title overlap = 2, platform overlap
            # = 0) and qBit downloaded the wrong rom.
            #
            # Pass 1: title AND platform overlap (≥ 1 each).
            # Pass 2 fallback: only when NO candidate anywhere
            # had any platform overlap — that means the
            # archive doesn't encode platform info in paths
            # (e.g. an Erista single-platform release), so
            # title-only is the best we can do.
            # Slice 437 — pre-filter to ``allowed_extensions``
            # when the caller provided them. Pre-slice the loop
            # scored every file in the torrent, which meant a
            # PSN ``.rap`` license token sitting next to the
            # real ``.chd`` in a meta-torrent's per-game folder
            # scored identically on the parent-dir tokens (same
            # "Crash", "Bandicoot", "Warped" tokens from the
            # folder) and could win alphabetically. The .chd
            # downloaded but the user's queue ended up pointing
            # at the 16-byte .rap, which the importer then
            # dumped as the game's release.
            #
            # ``allowed_extensions`` comes from grab.py querying
            # ``platform_format`` for the target game's platform
            # — built-in pack + user additions, no hardcoded
            # sets in the download-client layer. ``None`` keeps
            # the legacy any-extension scoring for callers that
            # don't know the platform yet (scan-driven imports,
            # tests).
            title_matches: list[tuple[int, int, int]] = []  # idx, t_ov, p_ov
            any_platform_overlap = False
            for idx, entry in enumerate(files):
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "")
                if not name:
                    continue
                if allowed_extensions is not None:
                    suffix = (
                        f".{name.rsplit('.', 1)[-1].lower()}"
                        if "." in name
                        else ""
                    )
                    if suffix not in allowed_extensions:
                        continue
                path_tokens = _significant_path_tokens(name)
                title_overlap = len(title_tokens & path_tokens)
                platform_overlap = len(platform_tokens & path_tokens)
                if platform_overlap > 0:
                    any_platform_overlap = True
                if title_overlap == 0:
                    continue
                title_matches.append((idx, title_overlap, platform_overlap))

            strict = [m for m in title_matches if m[2] > 0]
            pool = strict if strict else (
                title_matches if not any_platform_overlap else []
            )
            if not pool:
                logger.warning(
                    "qbit.select_only_matching_file.no_platform_match "
                    "native_id=%s title=%s platform=%s candidates=%d",
                    client_native_id,
                    sorted(title_tokens),
                    sorted(platform_tokens),
                    len(title_matches),
                )
                # Block the torrent from downloading anything —
                # we know the operator's target file isn't in
                # this archive. Caller (grab.py) sees the None
                # return and the queue_entry stays as-is for
                # manual cleanup, but at least qBit doesn't
                # wander off downloading 7.6 TB.
                all_ids = "|".join(str(i) for i in range(len(files)))
                if all_ids:
                    await self._post(
                        client,
                        "/torrents/filePrio",
                        data={
                            "hash": client_native_id.lower(),
                            "id": all_ids,
                            "priority": "0",
                        },
                    )
                return None

            best_idx, _, _ = max(pool, key=lambda m: (m[1], m[2]))

            other_ids = "|".join(
                str(i) for i in range(len(files)) if i != best_idx
            )
            # Two POSTs — qBit's filePrio takes one priority value
            # at a time but accepts a list of file ids.
            if other_ids:
                await self._post(
                    client,
                    "/torrents/filePrio",
                    data={
                        "hash": client_native_id.lower(),
                        "id": other_ids,
                        "priority": "0",
                    },
                )
            await self._post(
                client,
                "/torrents/filePrio",
                data={
                    "hash": client_native_id.lower(),
                    "id": str(best_idx),
                    "priority": "1",
                },
            )
            picked = files[best_idx]
            return str(picked.get("name") or "")

    # ---- internals ------------------------------------------------------------

    async def _wait_for_metadata(
        self,
        client: httpx.AsyncClient,
        info_hash: str,
        *,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> bool:
        """Slice 417 — block until qBit reports ``has_metadata=true``
        for the given hash, or ``timeout`` seconds elapse.

        Magnet adds give qBit only the info-hash; the file list
        comes later via the DHT/peer metadata exchange. Reading
        ``/torrents/files`` before metadata is in returns an
        empty list, so callers (slice 416's filePrio narrowing)
        must wait or they silently no-op and qBit downloads the
        whole torrent.

        Returns ``True`` once ``has_metadata`` flips to true,
        ``False`` on timeout. qBit's piece-request engine is
        gated on metadata anyway, so no data is downloaded
        during the wait — the only cost is the operator
        watching a brief delay between grab and download start.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            row = await self._fetch_torrent_by_hash(client, info_hash)
            if row is not None and bool(row.get("has_metadata")):
                return True
            await asyncio.sleep(interval)
        return False

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

        Raises :class:`DownloaderError` on 4xx / 5xx so the
        caller doesn't fall through to qBit's silent failure
        path (slice 406 — the user observed a Prowlarr 429 on
        the download URL leading qBit to list the *previous*
        torrent in the category as the "just-added" one,
        polluting the queue_entry with a stale hash).
        """
        try:
            # Slice 420 — share the download client's configured
            # timeout. Indexers that proxy through a slow upstream
            # (Prowlarr -> Grabarr) routinely take past 15 s; the
            # operator now controls this from Settings → Download
            # Clients.
            async with httpx.AsyncClient(
                timeout=self._timeout,
                verify=self._verify,
                follow_redirects=False,
            ) as probe:
                response = await probe.get(url)
        except httpx.HTTPError as exc:
            raise DownloaderError(
                f"indexer download URL fetch failed: {exc}"
            ) from exc

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
            # 200 OK with non-torrent payload — let qBit have a
            # shot (might be HTML the operator can debug).
            return None

        # 4xx / 5xx from the indexer (Prowlarr 429 is the common
        # case). Surfacing as a DownloaderError keeps the grab
        # flow from silently storing a stale hash via
        # ``_discover_added_hash``.
        raise DownloaderError(
            f"indexer download URL returned HTTP {response.status_code} — "
            "the torrent file was not delivered (likely rate-limited)"
        )

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
