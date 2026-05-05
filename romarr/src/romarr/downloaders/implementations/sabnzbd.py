"""SABnzbd download client.

SAB exposes a simple query-string API at ``{scheme}://{host}:{port}{base}/api``.
Every operation is a GET (or multipart POST for ``addfile``) with
``mode=...&apikey=...&output=json`` plus mode-specific parameters.

Per Article VIII: no third-party SAB Python client — direct httpx
against the documented endpoints. The wire format is stable and the
surface we use (``addurl``, ``addfile``, ``queue``, ``history``,
``get_cats``, ``version``, ``delete``) is documented in SAB's
``/api?mode=API``.

Auth model: SAB returns HTTP 200 with ``{"status": false,
"error": "API Key Incorrect"}`` on bad keys. We translate that to
:class:`romarr.downloaders.errors.AuthError` so the connectivity
orchestrator's ``error_code='auth'`` envelope is consistent across
clients.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    DownloaderError,
    TLSError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.tags import TAG_ROMARR
from romarr.downloaders.tls import SslCertValidation, build_httpx_verify
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    DownloadStatus,
    ManagedDownload,
    NzbBytes,
    NzbSource,
    NzbUrl,
    TorrentSource,
)


class SabnzbdClient(DownloadClient):
    """SABnzbd implementation of the download-client ABC.

    The class is initialized once per configured row and re-used —
    callers that want a fresh httpx connection pool should construct
    a new instance.
    """

    client_type: ClassVar[ClientType] = ClientType.SABNZBD
    supports_torrents: ClassVar[bool] = False
    supports_usenet: ClassVar[bool] = True

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
        timeout_seconds: float = 15.0,
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

    @property
    def base_url(self) -> str:
        """The fully-qualified ``/api`` endpoint."""
        return (
            f"{self._scheme}://{self._host}:{self._port}{self._url_base}/api"
        )

    # ---- low-level call -------------------------------------------------------

    async def _call(
        self,
        mode: str,
        *,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        **params: str,
    ) -> dict[str, Any]:
        """Issue one SAB API call and return the parsed JSON body.

        ``files`` is set only by ``addfile``'s multipart upload; the
        other modes are bare GETs. Errors are translated to typed
        :mod:`romarr.downloaders.errors` exceptions so callers don't
        introspect httpx state.
        """
        query: dict[str, str] = {
            "mode": mode,
            "apikey": self._api_key,
            "output": "json",
            **params,
        }

        try:
            async with httpx.AsyncClient(
                verify=self._verify, timeout=self._timeout
            ) as client:
                if files is not None:
                    response = await client.post(
                        self.base_url, params=query, files=files
                    )
                else:
                    response = await client.get(self.base_url, params=query)
        except httpx.TimeoutException as exc:
            raise DownloaderConnError(f"SABnzbd timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            # httpx wraps SSL errors as ConnectError; sniff the message.
            if "ssl" in str(exc).lower() or "certificate" in str(exc).lower():
                raise TLSError(f"SABnzbd TLS handshake failed: {exc}") from exc
            raise DownloaderConnError(
                f"SABnzbd unreachable: {exc}"
            ) from exc
        except httpx.TransportError as exc:  # pragma: no cover — defensive
            raise DownloaderConnError(
                f"SABnzbd transport error: {exc}"
            ) from exc

        # SAB returns 200 even on bad apikey; the body's ``status: false``
        # is the authoritative auth-failure signal.
        if response.status_code in (401, 403):
            raise AuthError(f"SABnzbd auth failed: HTTP {response.status_code}")
        if response.status_code >= 500:
            raise DownloaderConnError(
                f"SABnzbd server error: HTTP {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise DownloaderError(
                f"SABnzbd returned non-JSON body: {response.text[:200]}"
            ) from exc

        # ``{"status": false, "error": "..."}`` — auth or generic failure.
        if isinstance(data, dict) and data.get("status") is False:
            error_msg = str(data.get("error", "unknown SABnzbd error"))
            if "api key" in error_msg.lower():
                raise AuthError(f"SABnzbd: {error_msg}")
            raise DownloaderError(f"SABnzbd: {error_msg}")

        return data if isinstance(data, dict) else {"_raw": data}

    # ---- ABC contract ---------------------------------------------------------

    async def test_connection(self) -> str:
        data = await self._call("version")
        version = data.get("version")
        if not isinstance(version, str):
            raise DownloaderError("SABnzbd did not return a version string")
        return f"SABnzbd v{version}"

    async def ensure_category(self) -> None:
        """Check that the operator-configured category exists in SAB.

        SAB has no API to create a category — the operator does it
        manually in the UI. So this method is a check + warn, not a
        check + create.
        """
        data = await self._call("get_cats")
        categories = data.get("categories", [])
        if self._category not in categories:
            raise CategoryWarning(
                f"SABnzbd category {self._category!r} is missing — "
                f"create it manually in SAB Settings → Categories"
            )

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        raise NotImplementedError("SABnzbd does not handle torrents")

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        if isinstance(source, NzbUrl):
            data = await self._call(
                "addurl",
                name=str(source.url),
                cat=category,
            )
        elif isinstance(source, NzbBytes):
            data = await self._call(
                "addfile",
                files={
                    "nzbfile": ("upload.nzb", source.data, "application/x-nzb")
                },
                cat=category,
            )
        else:  # pragma: no cover — guarded by the discriminated union
            raise TypeError(f"unsupported NzbSource: {type(source)!r}")

        nzo_ids = data.get("nzo_ids") or []
        if not nzo_ids or not isinstance(nzo_ids[0], str):
            raise DownloaderError(
                f"SABnzbd add_nzb returned no nzo_ids: {data!r}"
            )
        return str(nzo_ids[0])

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        """Look the entry up in the active queue first, then fall back
        to history if it's already done."""
        queue = await self._call("queue")
        queue_block = queue.get("queue") or {}
        # ``kbpersec`` is reported on the queue block, not per-slot.
        kbpersec = _coerce_int(queue_block.get("kbpersec"))
        for slot in queue_block.get("slots", []):
            if slot.get("nzo_id") == client_native_id:
                return _build_queue_status(
                    self.client_id,
                    slot,
                    queue_kbpersec=kbpersec,
                    fetched_at=datetime.now(UTC),
                )

        history = await self._call("history", value=client_native_id)
        history_block = history.get("history") or {}
        for slot in history_block.get("slots", []):
            if slot.get("nzo_id") == client_native_id:
                return _build_history_status(
                    self.client_id, slot, fetched_at=datetime.now(UTC)
                )

        raise DownloaderError(
            f"SABnzbd has no record of nzo_id={client_native_id!r}"
        )

    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        # SAB's queue delete API: mode=queue&name=delete&value=<nzo_id>&del_files=1
        await self._call(
            "queue",
            name="delete",
            value=client_native_id,
            del_files="1" if delete_files else "0",
        )

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        """List romarr-managed completed history entries.

        SAB has no tag concept (per :meth:`set_imported_tag`'s no-op
        comment) so the watcher loop's dedup runs purely off the
        ``seen`` set. Status is filtered to ``Completed`` and the
        history is scoped to the operator-configured category.
        """
        history = await self._call("history", category=self._category)
        history_block = history.get("history") or {}
        out: list[ManagedDownload] = []
        for slot in history_block.get("slots", []):
            if not isinstance(slot, dict):
                continue
            status = str(slot.get("status") or "")
            if status != "Completed":
                continue
            native_id = str(slot.get("nzo_id") or "")
            if not native_id:
                continue
            out.append(
                ManagedDownload(
                    client_id=self.client_id,
                    client_native_id=native_id,
                    name=str(slot.get("name") or native_id),
                    save_path=str(slot.get("storage") or ""),
                    imported=False,
                )
            )
        return out

    async def set_imported_tag(self, client_native_id: str) -> None:
        """SAB has no tag concept; the lifecycle policy reads category
        membership instead. No-op here so the orchestrator can call
        the method uniformly across clients (FR-013).
        """
        return None


# ---------------------------------------------------------------------------
# Status mappers
# ---------------------------------------------------------------------------


_QUEUE_STATE_MAP: dict[str, DownloadState] = {
    "Queued": DownloadState.QUEUED,
    "Downloading": DownloadState.DOWNLOADING,
    "Paused": DownloadState.PAUSED,
    "Completed": DownloadState.COMPLETED,
    "Verifying": DownloadState.DOWNLOADING,
    "Repairing": DownloadState.DOWNLOADING,
    "Extracting": DownloadState.DOWNLOADING,
    "Failed": DownloadState.FAILED,
    "Stalled": DownloadState.STALLED,
}


def _coerce_int(value: object) -> int | None:
    """SAB serialises numerics as strings inconsistently; defend against both."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _build_queue_status(
    client_id: int,
    slot: dict[str, Any],
    *,
    queue_kbpersec: int | None,
    fetched_at: datetime,
) -> DownloadStatus:
    state_raw = str(slot.get("status", "Queued"))
    state = _QUEUE_STATE_MAP.get(state_raw, DownloadState.QUEUED)
    percent = float(slot.get("percentage", 0)) / 100.0
    eta = _eta_to_seconds(slot.get("timeleft"))
    download_rate_bps = (
        queue_kbpersec * 1000 if queue_kbpersec else None
    )

    return DownloadStatus(
        client_id=client_id,
        client_native_id=str(slot.get("nzo_id", "")),
        name=str(slot.get("filename", "")),
        state=state,
        progress=max(0.0, min(1.0, percent)),
        eta_seconds=eta,
        seeders=None,   # Usenet — no peers
        peers=None,
        download_rate_bps=download_rate_bps,
        upload_rate_bps=None,
        save_path=str(slot.get("path") or "") or None,
        completed_paths=[],
        fetched_at=fetched_at,
    )


def _build_history_status(
    client_id: int, slot: dict[str, Any], *, fetched_at: datetime
) -> DownloadStatus:
    state_raw = str(slot.get("status", "Completed"))
    state = (
        DownloadState.COMPLETED
        if state_raw == "Completed"
        else _QUEUE_STATE_MAP.get(state_raw, DownloadState.FAILED)
    )
    storage = str(slot.get("storage") or slot.get("path") or "")
    return DownloadStatus(
        client_id=client_id,
        client_native_id=str(slot.get("nzo_id", "")),
        name=str(slot.get("name") or slot.get("filename", "")),
        state=state,
        progress=1.0 if state is DownloadState.COMPLETED else 0.0,
        eta_seconds=None,
        seeders=None,
        peers=None,
        download_rate_bps=None,
        upload_rate_bps=None,
        save_path=storage or None,
        completed_paths=[storage] if storage and state is DownloadState.COMPLETED else [],
        fetched_at=fetched_at,
    )


def _eta_to_seconds(value: object) -> int | None:
    """Parse SAB's HH:MM:SS string into seconds. Returns None on parse failure."""
    if not isinstance(value, str) or not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


__all__ = ["SabnzbdClient"]
