"""Connectivity orchestrator tests (T017-T019)."""

from __future__ import annotations

from typing import ClassVar

import pytest

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.connectivity import (
    test_connectivity as connectivity_probe,
)
from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    TLSError,
    VersionError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.types import (
    ClientType,
    DownloadStatus,
    NzbSource,
    TorrentSource,
)


class _FakeClient(DownloadClient):
    """Test double — every method is overridable per-test."""

    client_type: ClassVar[ClientType] = ClientType.QBITTORRENT
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False

    def __init__(
        self,
        *,
        version: str = "FakeClient v1.0.0",
        connect_error: BaseException | None = None,
        category_error: BaseException | None = None,
    ) -> None:
        super().__init__(client_id=1, name="Fake")
        self._version = version
        self._connect_error = connect_error
        self._category_error = category_error

    async def test_connection(self) -> str:
        if self._connect_error is not None:
            raise self._connect_error
        return self._version

    async def ensure_category(self) -> None:
        if self._category_error is not None:
            raise self._category_error

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        raise NotImplementedError  # pragma: no cover

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        raise NotImplementedError  # pragma: no cover

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        raise NotImplementedError  # pragma: no cover

    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        raise NotImplementedError  # pragma: no cover

    async def set_imported_tag(self, client_native_id: str) -> None:
        raise NotImplementedError  # pragma: no cover

    async def list_managed_downloads(self) -> list:
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# T017 — happy path returns structured result
# ---------------------------------------------------------------------------


async def test_returns_structured_result_on_happy_path() -> None:
    client = _FakeClient(version="qBittorrent v4.6.5")
    result = await connectivity_probe(client)
    assert result.ok is True
    assert result.error_code is None
    assert result.client_version == "qBittorrent v4.6.5"
    assert result.warnings == []


# ---------------------------------------------------------------------------
# T018 — typed errors fan out to error_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (DownloaderConnError("conn refused"), "connection"),
        (AuthError("bad creds"), "auth"),
        (TLSError("bad cert"), "tls"),
        (VersionError("too old"), "version"),
    ],
)
async def test_typed_errors_translate_to_error_code(
    error: BaseException, expected_code: str
) -> None:
    client = _FakeClient(connect_error=error)
    result = await connectivity_probe(client)
    assert result.ok is False
    assert result.error_code == expected_code
    assert result.error_message is not None


# ---------------------------------------------------------------------------
# T019 — warnings non-blocking (ok=True)
# ---------------------------------------------------------------------------


async def test_category_warning_does_not_fail_the_test() -> None:
    client = _FakeClient(
        category_error=CategoryWarning(
            "category 'romarr' is missing — create it manually"
        )
    )
    result = await connectivity_probe(client)
    assert result.ok is True
    assert result.error_code is None
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == "category_missing"
    assert "romarr" in warning.message


async def test_no_warnings_when_category_present() -> None:
    client = _FakeClient()
    result = await connectivity_probe(client)
    assert result.warnings == []


# ---------------------------------------------------------------------------
# Internal error fallback
# ---------------------------------------------------------------------------


async def test_unknown_downloader_error_translates_to_internal() -> None:
    from romarr.downloaders.errors import DownloaderError

    client = _FakeClient(connect_error=DownloaderError("weird thing"))
    result = await connectivity_probe(client)
    assert result.ok is False
    assert result.error_code == "internal"


async def test_ensure_category_not_implemented_skipped_silently() -> None:
    """Stub clients raise NotImplementedError from ensure_category;
    the orchestrator must NOT crash on them — they simply have no
    category to verify."""
    client = _FakeClient(
        category_error=NotImplementedError("deferred to v1")
    )
    result = await connectivity_probe(client)
    assert result.ok is True
    assert result.warnings == []
