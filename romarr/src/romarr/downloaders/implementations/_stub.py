"""Shared base for the three v1-deferred client stubs.

Each concrete stub (Transmission, Deluge, NZBGet) sets its
``client_type`` and capability flags then inherits the
``NotImplementedError`` contract below. The error message MUST be
``"deferred to v1"`` so the schema endpoint and any caller can
machine-parse the reason (T040-T042 assert against this exact text).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from romarr.downloaders.base import DownloadClient

if TYPE_CHECKING:
    from romarr.downloaders.types import (
        ClientType,
        DownloadStatus,
        NzbSource,
        TorrentSource,
    )

_DEFERRED_MSG = "deferred to v1"


class _StubClient(DownloadClient):
    """Common ABC for the three v1-deferred stubs."""

    client_type: ClassVar[ClientType]
    available: ClassVar[bool] = False

    async def test_connection(self) -> str:
        raise NotImplementedError(_DEFERRED_MSG)

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        raise NotImplementedError(_DEFERRED_MSG)

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        raise NotImplementedError(_DEFERRED_MSG)

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        raise NotImplementedError(_DEFERRED_MSG)

    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        raise NotImplementedError(_DEFERRED_MSG)

    async def set_imported_tag(self, client_native_id: str) -> None:
        raise NotImplementedError(_DEFERRED_MSG)


__all__ = ["_StubClient"]
