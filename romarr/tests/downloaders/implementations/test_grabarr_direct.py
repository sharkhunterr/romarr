"""GrabarrDirectClient — slice 424 protocol-wiring tests.

Replaces the foundation stub tests (slice 422) now that the
implementation actually talks to Grabarr's ``/health`` + ``/resolve``
endpoints via httpx. Disk transfers and qBit magnet delegation
land in R2d — the ``torrent_magnet`` branch deliberately raises
:class:`NotImplementedError` here and is tested against that
contract so R2d's flip lights up loudly.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.downloaders.errors import (
    AuthError,
    DownloaderError,
    VersionError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.implementations.grabarr_direct import (
    SUPPORTED_PROTOCOL_VERSION,
    GrabarrDirectClient,
)
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    TorrentBytes,
    TorrentMagnet,
    TorrentUrl,
)


_BASE = "http://grabarr.test:8080"


def _client() -> GrabarrDirectClient:
    return GrabarrDirectClient(
        client_id=42,
        name="Grabarr direct",
        host="grabarr.test",
        port=8080,
        api_key="rmk_test_key",
    )


def _torznab_url(token: str = "abc123", slug: str = "roms_all") -> str:
    return f"{_BASE}/torznab/{slug}/download/{token}.torrent"


# ---- class-level metadata ------------------------------------------------


def test_class_metadata() -> None:
    assert GrabarrDirectClient.client_type is ClientType.GRABARR_DIRECT
    assert GrabarrDirectClient.supports_torrents is True
    assert GrabarrDirectClient.supports_usenet is False
    # R3 "Add Grabarr" wizard flips this on. Until then the type
    # is hidden from the Add Download Client modal.
    assert GrabarrDirectClient.available is False


def test_base_url_layout() -> None:
    assert _client().base_url == "http://grabarr.test:8080"
    assert GrabarrDirectClient(
        client_id=1, name="x", host="g.test", port=443,
        api_key="k", use_ssl=True, url_base="/grabarr",
    ).base_url == "https://g.test:443/grabarr"


# ---- test_connection -----------------------------------------------------


@respx.mock
async def test_connection_happy_path() -> None:
    respx.get(f"{_BASE}/romarr/api/v1/health").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": "1.2.1",
                "protocol_version": SUPPORTED_PROTOCOL_VERSION,
                "sources": ["internet_archive", "minerva"],
            },
        )
    )
    assert await _client().test_connection() == "1.2.1"


@respx.mock
async def test_connection_protocol_mismatch_raises_version_error() -> None:
    respx.get(f"{_BASE}/romarr/api/v1/health").mock(
        return_value=httpx.Response(
            200,
            json={"version": "9.9.9", "protocol_version": 2, "sources": []},
        )
    )
    with pytest.raises(VersionError, match="protocol_version"):
        await _client().test_connection()


@respx.mock
async def test_connection_401_raises_auth() -> None:
    respx.get(f"{_BASE}/romarr/api/v1/health").mock(
        return_value=httpx.Response(401, text="bad apikey")
    )
    with pytest.raises(AuthError):
        await _client().test_connection()


@respx.mock
async def test_connection_5xx_raises_connection_error() -> None:
    respx.get(f"{_BASE}/romarr/api/v1/health").mock(
        return_value=httpx.Response(503, text="gateway down")
    )
    with pytest.raises(DownloaderConnError, match="503"):
        await _client().test_connection()


@respx.mock
async def test_connection_network_error_raises_connection_error() -> None:
    respx.get(f"{_BASE}/romarr/api/v1/health").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(DownloaderConnError, match="cannot reach"):
        await _client().test_connection()


# ---- add_torrent: URL parsing + source-kind discipline -------------------


async def test_add_torrent_rejects_magnet_source() -> None:
    with pytest.raises(ValueError, match="not a magnet"):
        await _client().add_torrent(
            TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:dead"),
            category="romarr",
            tags=[],
        )


async def test_add_torrent_rejects_raw_bytes_source() -> None:
    with pytest.raises(ValueError, match="not raw torrent bytes"):
        await _client().add_torrent(
            TorrentBytes(data=b"d8:announce..."),
            category="romarr",
            tags=[],
        )


async def test_add_torrent_rejects_non_torznab_url() -> None:
    with pytest.raises(ValueError, match="does not look like"):
        await _client().add_torrent(
            TorrentUrl(url="https://example.test/some/random.torrent"),
            category="romarr",
            tags=[],
        )


# ---- add_torrent: /resolve dispatch --------------------------------------


@respx.mock
async def test_add_torrent_http_direct_stashes_and_returns_native_id() -> None:
    token = "tokABC"
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "http_direct",
                "filename": "GoldenEye 007 (USA).z64",
                "url": "https://ia801234.us.archive.org/12/items/n64/g.z64",
                "expected_size": 12582912,
                "headers": {"User-Agent": "ua"},
                "checksums": {"sha1": "deadbeef"},
                "source": "internet_archive",
                "expires_at": "2026-05-13T15:00:00+00:00",
            },
        )
    )
    client = _client()
    native_id = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=["romarr", "romarr-n64"],
    )
    assert native_id == f"grabarr-{token}"
    snap = client._pending[native_id]  # noqa: SLF001 — test-only introspection
    assert snap["method"] == "http_direct"
    assert snap["filename"] == "GoldenEye 007 (USA).z64"
    assert snap["expected_size"] == 12582912
    assert snap["url"].endswith("/g.z64")
    assert snap["checksums"] == {"sha1": "deadbeef"}
    assert snap["category"] == "romarr"
    assert "romarr-n64" in snap["tags"]


@respx.mock
async def test_add_torrent_torrent_magnet_raises_not_implemented_for_now() -> None:
    """R2c surfaces the gap loudly so R2d's flip is detected by
    every test that touched this branch."""
    token = "tokMagnet"
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "torrent_magnet",
                "magnet_uri": "magnet:?xt=urn:btih:abc123def456",
                "filename": "Mario 64 (USA).z64",
                "filename_hint": "Mario 64 (USA).z64",
                "expected_size": 8388608,
                "headers": {},
                "checksums": {},
                "source": "vimm",
                "expires_at": "2026-05-13T15:00:00+00:00",
            },
        )
    )
    client = _client()
    with pytest.raises(NotImplementedError, match="R2d"):
        await client.add_torrent(
            TorrentUrl(url=_torznab_url(token=token)),
            category="romarr",
            tags=[],
        )
    # The entry was still stashed before the raise so R2d's flip
    # can pick up exactly where this one left off.
    assert f"grabarr-{token}" in client._pending  # noqa: SLF001


@respx.mock
async def test_add_torrent_unknown_method_raises() -> None:
    token = "tokWeird"
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"method": "warp_drive", "expires_at": "2026-05-13T00:00:00Z"},
        )
    )
    with pytest.raises(DownloaderError, match="unknown resolve method"):
        await _client().add_torrent(
            TorrentUrl(url=_torznab_url(token=token)),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_401_raises_auth() -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokAuth"
    ).mock(return_value=httpx.Response(401, json={"code": "unauthenticated"}))
    with pytest.raises(AuthError):
        await _client().add_torrent(
            TorrentUrl(url=_torznab_url(token="tokAuth")),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_403_raises_auth() -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokWrongProfile"
    ).mock(return_value=httpx.Response(403, json={"code": "forbidden"}))
    with pytest.raises(AuthError, match="different profile"):
        await _client().add_torrent(
            TorrentUrl(url=_torznab_url(token="tokWrongProfile")),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_expired_token_raises() -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokExpired"
    ).mock(return_value=httpx.Response(404, json={"code": "guid_not_found"}))
    with pytest.raises(DownloaderError, match="expired or unknown"):
        await _client().add_torrent(
            TorrentUrl(url=_torznab_url(token="tokExpired")),
            category="romarr",
            tags=[],
        )


# ---- lifecycle placeholders (R2d makes them real) ------------------------


@respx.mock
async def test_get_status_returns_queued_for_pending_entry() -> None:
    token = "tokStatus"
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "http_direct",
                "filename": "x.zip",
                "url": "https://example.test/x.zip",
                "expected_size": 100,
                "headers": {},
                "checksums": {},
                "source": "internet_archive",
                "expires_at": "2026-05-13T00:00:00Z",
            },
        )
    )
    client = _client()
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    status = await client.get_status(nid)
    # R2c is inert — entries stay QUEUED. R2d advances them to
    # DOWNLOADING / COMPLETED as the httpx stream progresses.
    assert status.state is DownloadState.QUEUED
    assert status.progress == 0.0
    assert status.total_bytes == 100
    assert status.client_native_id == nid
    assert status.client_id == 42


async def test_get_status_unknown_native_id_raises() -> None:
    with pytest.raises(DownloaderError, match="unknown native_id"):
        await _client().get_status("grabarr-never-added")


async def test_remove_is_idempotent_on_missing_entry() -> None:
    # No raise — operators clicking "remove" twice should not crash.
    await _client().remove("grabarr-never-added", delete_files=False)


async def test_list_managed_downloads_is_empty_in_r2c() -> None:
    assert await _client().list_managed_downloads() == []


async def test_ensure_category_is_a_noop() -> None:
    await _client().ensure_category()  # no raise


async def test_set_imported_tag_is_a_noop() -> None:
    await _client().set_imported_tag("any-id")  # no raise


async def test_add_nzb_rejects_usenet() -> None:
    from romarr.downloaders.types import NzbUrl

    with pytest.raises(ValueError, match="does not accept Usenet"):
        await _client().add_nzb(
            NzbUrl(url="http://example.test/x.nzb"),
            category="romarr",
        )
