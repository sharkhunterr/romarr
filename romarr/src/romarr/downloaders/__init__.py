"""Download-clients subsystem (spec 005).

Slice 1 ships SCAF + PERS + ABC + STUBS:

  * Module skeleton (types, errors, tags, TLS helper).
  * Persistence: ``download_client`` table + Alembic ``0005`` (which
    also installs the deferred FK on ``indexer.download_client_id``).
  * Abstract :class:`DownloadClient` base class.
  * Three v1-deferred stubs (Transmission, Deluge, NZBGet) that
    raise ``NotImplementedError("deferred to v1")``.

qBittorrent + SABnzbd implementations, the connectivity tester,
routing, retry, and the admin API land in subsequent slices.
"""

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    ConnectionError,
    DownloaderError,
    NoEligibleClientError,
    TLSError,
    VersionError,
)
from romarr.downloaders.implementations import (
    DelugeClient,
    NzbgetClient,
    TransmissionClient,
)
from romarr.downloaders.routing import (
    RoutingCandidate,
    consume_decision,
    route_release,
    select_nzb_form,
    select_torrent_form,
)
from romarr.downloaders.tags import (
    TAG_IMPORTED,
    TAG_ROMARR,
    standard_tag_set,
    tag_for_platform,
)
from romarr.downloaders.tls import (
    SslCertValidation,
    build_httpx_verify,
    is_local_host,
)
from romarr.downloaders.types import (
    ClientType,
    ConnectivityTestResult,
    ConnectivityWarning,
    DownloadState,
    DownloadStatus,
    NzbBytes,
    NzbSource,
    NzbUrl,
    RoutingDecision,
    SourceKind,
    TorrentBytes,
    TorrentMagnet,
    TorrentSource,
    TorrentUrl,
)

__all__ = [
    "TAG_IMPORTED",
    "TAG_ROMARR",
    "AuthError",
    "CategoryWarning",
    "ClientType",
    "ConnectionError",
    "ConnectivityTestResult",
    "ConnectivityWarning",
    "DelugeClient",
    "DownloadClient",
    "DownloadState",
    "DownloadStatus",
    "DownloaderError",
    "NoEligibleClientError",
    "NzbBytes",
    "NzbSource",
    "NzbUrl",
    "NzbgetClient",
    "RoutingCandidate",
    "RoutingDecision",
    "SourceKind",
    "SslCertValidation",
    "TLSError",
    "TorrentBytes",
    "TorrentMagnet",
    "TorrentSource",
    "TorrentUrl",
    "TransmissionClient",
    "VersionError",
    "build_httpx_verify",
    "consume_decision",
    "is_local_host",
    "route_release",
    "select_nzb_form",
    "select_torrent_form",
    "standard_tag_set",
    "tag_for_platform",
]
