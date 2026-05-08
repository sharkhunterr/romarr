"""Value types for the download-clients feature.

Pure-Python (no DB, no I/O); consumed by the ABC, the implementations,
the routing engine, and the API. Persisted entities live in
:mod:`romarr.downloaders.models` + :mod:`romarr.downloaders.schemas`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ClientType(StrEnum):
    """The set of supported download-client implementations.

    The two MVP impls are ``QBITTORRENT`` and ``SABNZBD``; the three
    stubs surface in the registry / schema endpoint with
    ``available = False`` so the UI can grey them out.
    """

    QBITTORRENT = "qbittorrent"
    SABNZBD = "sabnzbd"
    TRANSMISSION = "transmission"  # stub — deferred to v1
    DELUGE = "deluge"              # stub — deferred to v1
    NZBGET = "nzbget"              # stub — deferred to v1


class SourceKind(StrEnum):
    """High-level source family driving routing.

    ``TORRENT`` covers magnet, ``.torrent`` URL, and raw ``.torrent``
    bytes. ``USENET`` covers ``.nzb`` URL and raw ``.nzb`` bytes.
    """

    TORRENT = "torrent"
    USENET = "usenet"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TorrentUrl(_Base):
    kind: Literal["torrent_url"] = "torrent_url"
    url: HttpUrl


class TorrentMagnet(_Base):
    kind: Literal["torrent_magnet"] = "torrent_magnet"
    magnet_uri: str


class TorrentBytes(_Base):
    kind: Literal["torrent_bytes"] = "torrent_bytes"
    data: bytes


# Discriminated union — Pydantic v2 picks the right concrete model
# off the ``kind`` literal. Source preference order
# (.torrent URL > .torrent bytes > magnet URL) is enforced by the
# routing layer (FR-003a).
TorrentSource = Annotated[
    TorrentUrl | TorrentMagnet | TorrentBytes,
    Field(discriminator="kind"),
]


class NzbUrl(_Base):
    kind: Literal["nzb_url"] = "nzb_url"
    url: HttpUrl


class NzbBytes(_Base):
    kind: Literal["nzb_bytes"] = "nzb_bytes"
    data: bytes


NzbSource = Annotated[
    NzbUrl | NzbBytes,
    Field(discriminator="kind"),
]


class DownloadState(StrEnum):
    """Canonical Romarr-side download state.

    Each implementation maps its native state vocabulary onto this
    enum; downstream consumers (UI, retry state machine, importer)
    only see this normalized form.
    """

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    SEEDING = "seeding"          # torrent only
    STALLED = "stalled"
    FAILED = "failed"


class ManagedDownload(_Base):
    """A completed download the importer can pick up (spec 008 FR-001).

    Yielded by :meth:`DownloadClient.list_managed_downloads`. Carries
    just enough to dispatch the import: the client + native id pair so
    the importer can correlate webhook + poll signals, and the
    on-disk save path so :func:`run_import` can hash + extract.

    The ``imported`` flag short-circuits the watcher's per-tick
    deduplication: clients that successfully tagged an item with the
    ``romarr-imported`` tag report ``imported=True`` so the loop skips
    them without consulting its in-memory ``seen`` set. Pure value
    object — no I/O, no DB.
    """

    client_id: int
    client_native_id: str
    name: str
    save_path: str
    imported: bool = False


class DownloadStatus(_Base):
    """One snapshot of a download's progress.

    ``client_native_id`` is the implementation-specific identifier
    (qBit info-hash, SAB nzo_id) — Romarr persists it on the future
    queue_entry row and uses it when issuing follow-up calls.
    ``seeders``/``peers``/``upload_rate_bps`` are NULL for Usenet
    (no peers).
    """

    client_id: int
    client_native_id: str
    name: str
    state: DownloadState
    progress: float = Field(ge=0.0, le=1.0)
    eta_seconds: int | None = None
    seeders: int | None = None
    peers: int | None = None
    download_rate_bps: int | None = None
    upload_rate_bps: int | None = None
    # Total bytes of the download as reported by the client
    # (qBit ``size`` / SAB ``mb`` × 1024²). NULL when the client
    # hasn't surfaced it yet — the reconciler then leaves the
    # row untouched. Slice 367 added the field; older
    # implementations that don't fill it stay backward-compat.
    total_bytes: int | None = None
    save_path: str | None = None
    completed_paths: list[str] = Field(default_factory=list)
    fetched_at: datetime


_WARNING_CODE = Literal[
    "category_missing",
    "version_old",
    "tls_disabled_for_local",
]


class ConnectivityWarning(_Base):
    """Non-blocking observation surfaced by the connectivity tester."""

    code: _WARNING_CODE
    message: str


_ERROR_CODE = Literal[
    "connection",
    "auth",
    "tls",
    "version",
    "internal",
]


class ConnectivityTestResult(_Base):
    """Outcome of one ``test_connectivity(impl)`` round-trip.

    The shape is intentionally flat (``ok`` + ``error_code``) so the
    UI doesn't need a try/except path — every failure mode round-trips
    through the same JSON envelope (FR-008, SC-006).
    """

    ok: bool
    error_code: _ERROR_CODE | None = None
    error_message: str | None = None
    client_version: str | None = None
    warnings: list[ConnectivityWarning] = Field(default_factory=list)


_ROUTE_VIA = Literal[
    "indexer_override",
    "priority",
    "no_eligible_client",
]


class RoutingDecision(_Base):
    """Pure-function routing output.

    ``chosen_client_id`` is ``None`` iff no client supports the
    source kind (or the override pin is unsuitable AND no fallback
    matches). Callers that need to act on the decision raise
    :class:`romarr.downloaders.errors.NoEligibleClientError` when
    ``chosen_via == 'no_eligible_client'``.
    """

    chosen_client_id: int | None
    chosen_via: _ROUTE_VIA
    source_kind: SourceKind
    candidates_considered: list[int] = Field(default_factory=list)
    rejection_reason: str | None = None


__all__ = [
    "ClientType",
    "ConnectivityTestResult",
    "ConnectivityWarning",
    "DownloadState",
    "DownloadStatus",
    "ManagedDownload",
    "NzbBytes",
    "NzbSource",
    "NzbUrl",
    "RoutingDecision",
    "SourceKind",
    "TorrentBytes",
    "TorrentMagnet",
    "TorrentSource",
    "TorrentUrl",
]
