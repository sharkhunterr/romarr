"""Abstract base class for download-client implementations.

Every concrete client (``QBittorrentClient``, ``SabnzbdClient``,
plus the v1 stubs) inherits from :class:`DownloadClient`. The class
ships:

  * Class-level metadata: ``client_type``, ``supports_torrents``,
    ``supports_usenet``, ``available``. Read by the registry / schema
    endpoint without instantiating the impl.
  * Async method contract: ``test_connection``, ``add_torrent`` /
    ``add_nzb``, ``get_status``, ``remove``, ``set_imported_tag``.
  * Each method is documented in terms of the typed errors it MAY
    raise so the connectivity tester (and the future grab orchestrator)
    can translate uniformly across implementations.

Slice 1 ships the contract + the three v1 stubs that raise
``NotImplementedError("deferred to v1")`` from every method.
qBittorrent + SABnzbd implementations land in slice 2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from romarr.downloaders.types import (
        ClientType,
        DownloadStatus,
        ManagedDownload,
        NzbSource,
        TorrentSource,
    )


class DownloadClient(ABC):
    """Async interface every concrete client implements.

    Subclasses override the four class-level attributes below to
    declare their identity and capabilities; the registry uses those
    to filter candidates during routing without an instance.
    """

    # ---- class-level metadata --------------------------------------------------

    client_type: ClassVar[ClientType]
    """The :class:`ClientType` literal this implementation handles."""

    supports_torrents: ClassVar[bool] = False
    """True iff this client can take torrent sources."""

    supports_usenet: ClassVar[bool] = False
    """True iff this client can take Usenet (.nzb) sources."""

    available: ClassVar[bool] = True
    """``False`` for v1-deferred stubs (transmission, deluge, nzbget)."""

    # ---- runtime configuration ------------------------------------------------

    def __init__(self, *, client_id: int, name: str) -> None:
        """Subclasses extend this with host/port/credentials kwargs.

        ``client_id`` is the row id in the ``download_client`` table;
        carried on every :class:`DownloadStatus` snapshot so the queue
        view can fan results out by client.
        """
        self.client_id = client_id
        self.name = name

    # ---- contract -------------------------------------------------------------

    @abstractmethod
    async def test_connection(self) -> str:
        """Probe the client; return its version string on success.

        Raises:
            ConnectionError: network-layer failure.
            AuthError:       credentials rejected.
            TLSError:        TLS handshake failed.
            VersionError:    the client is older than the supported floor.
        """

    @abstractmethod
    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        """Hand a torrent to the client; return the client-native id
        (info-hash for qBit). Idempotent on a repeat info-hash
        (FR-004a / CL001) — the existing entry's tags are merged
        additively rather than replaced.
        """

    @abstractmethod
    async def add_nzb(
        self,
        source: NzbSource,
        *,
        category: str,
    ) -> str:
        """Hand an NZB to the client; return the client-native id
        (nzo_id for SAB). Idempotent on a repeat source URL.
        """

    @abstractmethod
    async def get_status(self, client_native_id: str) -> DownloadStatus:
        """Return a :class:`DownloadStatus` snapshot for one item."""

    @abstractmethod
    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        """Remove an item from the client. ``delete_files=True`` also
        deletes the on-disk content (used by ``remove_failed_downloads``
        post-import or by lifecycle ``move + remove``).
        """

    @abstractmethod
    async def set_imported_tag(self, client_native_id: str) -> None:
        """Add the ``romarr-imported`` tag post-import (FR-013).

        SAB's tag model is per-job (``meta`` field); qBit uses the
        torrents/addTags endpoint. Both end up flagged so the
        lifecycle policy can act.
        """

    @abstractmethod
    async def list_managed_downloads(self) -> list[ManagedDownload]:
        """Return every Romarr-managed download the client knows about
        whose status is "completed and on disk" (spec 008 FR-001).

        Implementations MUST filter to the operator-configured
        category and SHOULD skip items already carrying the
        ``romarr-imported`` tag (or set ``imported=True`` on those
        records so the watcher loop's dedup can rely on the flag).

        Raises:
            ConnectionError: network-layer failure.
            AuthError:       credentials rejected.
        """

    @abstractmethod
    async def ensure_category(self) -> None:
        """Ensure the operator-configured category exists on the client.

        qBittorrent auto-creates the category (free API). SAB cannot —
        the operator MUST manually create the category in SAB's UI, so
        SAB raises :class:`CategoryWarning` when the category is missing.
        The connectivity orchestrator catches that warning and surfaces
        a non-blocking :class:`ConnectivityWarning` (FR-011).

        Raises:
            CategoryWarning: when the category is missing and cannot be
                created automatically.
        """


__all__ = ["DownloadClient"]
