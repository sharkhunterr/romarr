"""GrabarrDirectClient — slice 425 streaming-implementation tests.

Replaces the slice 424 contract-only tests now that the http_direct
branch actually pulls bytes to disk via httpx. The torrent_magnet
branch still raises a (clearer) ``NotImplementedError`` until R2e
wires the qBit delegation through the dispatcher, and that
transition is pinned by a dedicated test.

Each streaming test injects ``tmp_path`` as ``download_root`` so
no test ever writes outside the pytest tmpdir.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

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
_FILE_HOST = "http://ia.test"


def _client(tmp_path: Path | None = None) -> GrabarrDirectClient:
    return GrabarrDirectClient(
        client_id=42,
        name="Grabarr direct",
        host="grabarr.test",
        port=8080,
        api_key="rmk_test_key",
        download_root=tmp_path if tmp_path is not None else Path("/tmp"),
    )


def _torznab_url(token: str = "abc123", slug: str = "roms_all") -> str:
    return f"{_BASE}/torznab/{slug}/download/{token}.torrent"


def _http_direct_resolve(
    *, url: str = f"{_FILE_HOST}/files/sample.zip",
    filename: str = "sample.zip",
    size: int = 12,
    checksums: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "method": "http_direct",
        "filename": filename,
        "url": url,
        "expected_size": size,
        "headers": {},
        "checksums": checksums or {},
        "source": "internet_archive",
        "expires_at": "2026-05-13T00:00:00Z",
    }


# ---- class-level metadata ------------------------------------------------


def test_class_metadata() -> None:
    assert GrabarrDirectClient.client_type is ClientType.GRABARR_DIRECT
    assert GrabarrDirectClient.supports_torrents is True
    assert GrabarrDirectClient.supports_usenet is False
    # Slice 427 / R3a — the wizard endpoint ships, so the class
    # declares itself available. The Add Download Client modal
    # still hides it (``_CLIENT_TYPES`` array unchanged) because
    # the dedicated wizard is the supported entry path.
    assert GrabarrDirectClient.available is True


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


async def test_add_torrent_rejects_magnet_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a magnet"):
        await _client(tmp_path).add_torrent(
            TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:dead"),
            category="romarr",
            tags=[],
        )


async def test_add_torrent_rejects_raw_bytes_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not raw torrent bytes"):
        await _client(tmp_path).add_torrent(
            TorrentBytes(data=b"d8:announce..."),
            category="romarr",
            tags=[],
        )


async def test_add_torrent_rejects_non_torznab_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not look like"):
        await _client(tmp_path).add_torrent(
            TorrentUrl(url="https://example.test/some/random.torrent"),
            category="romarr",
            tags=[],
        )


# ---- http_direct streaming -----------------------------------------------


@respx.mock
async def test_http_direct_streams_to_disk_and_marks_completed(
    tmp_path: Path,
) -> None:
    token = "tokStream"
    body = b"ROM-BYTES-12"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200, json=_http_direct_resolve(size=len(body))
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-length": str(len(body))}
        )
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=["romarr"],
    )
    assert nid == f"grabarr-{token}"
    await client.wait_for_task(nid)

    status = await client.get_status(nid)
    assert status.state is DownloadState.COMPLETED
    assert status.progress == 1.0
    assert status.total_bytes == len(body)
    expected_path = tmp_path / "romarr" / "sample.zip"
    assert status.save_path == str(expected_path)
    assert status.completed_paths == [str(expected_path)]
    assert expected_path.read_bytes() == body


@respx.mock
async def test_http_direct_uses_explicit_save_path_when_supplied(
    tmp_path: Path,
) -> None:
    token = "tokExplicit"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(200, json=_http_direct_resolve(size=4))
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200, content=b"abcd", headers={"content-length": "4"}
        )
    )
    custom = tmp_path / "custom" / "explicit.bin"

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
        save_path=str(custom),
    )
    await client.wait_for_task(nid)
    assert custom.exists()
    assert custom.read_bytes() == b"abcd"


@respx.mock
async def test_http_direct_sanitises_unsafe_filename(tmp_path: Path) -> None:
    token = "tokUnsafe"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(
                filename="../../etc/passwd", size=3,
            ),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(200, content=b"xxx")
    )
    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    snap = client._pending[nid]  # noqa: SLF001
    # Stripped to the final segment only — no parent traversal.
    assert snap["save_path"] == str(tmp_path / "romarr" / "passwd")


@respx.mock
async def test_http_direct_upstream_4xx_marks_failed_and_removes_file(
    tmp_path: Path,
) -> None:
    token = "tok4xx"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(200, json=_http_direct_resolve(size=10))
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(404, text="gone")
    )
    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    status = await client.get_status(nid)
    assert status.state is DownloadState.FAILED
    snap = client._pending[nid]  # noqa: SLF001
    assert "404" in (snap["error"] or "")
    # File must not linger after a failure (the writer creates the
    # path before the stream loop; the cleanup pass deletes it).
    assert not Path(snap["save_path"]).exists()


# ---- slice 429 / R4 — checksum verification ------------------------------


@respx.mock
async def test_http_direct_verifies_matching_checksums(
    tmp_path: Path,
) -> None:
    """Slice 429 / R4 — when the resolve response carries sha1 /
    md5 / crc32, the streamer computes them incrementally and
    accepts the download on a full match. ``computed_checksums``
    on the pending snap mirrors the values for diagnostics."""
    import hashlib
    import zlib

    token = "tokVerify"
    body = b"ROM-BYTES-12"
    sha1 = hashlib.sha1(body).hexdigest()
    md5 = hashlib.md5(body).hexdigest()
    crc32 = f"{zlib.crc32(body) & 0xFFFFFFFF:08x}"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(
                size=len(body),
                checksums={"sha1": sha1, "md5": md5, "crc32": crc32},
            ),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-length": str(len(body))}
        )
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)

    status = await client.get_status(nid)
    assert status.state is DownloadState.COMPLETED
    snap = client._pending[nid]  # noqa: SLF001
    assert snap["computed_checksums"]["sha1"] == sha1
    assert snap["computed_checksums"]["md5"] == md5
    assert snap["computed_checksums"]["crc32"] == crc32
    # File matches the bytes we asked for.
    expected_path = tmp_path / "romarr" / "sample.zip"
    assert expected_path.read_bytes() == body


@respx.mock
async def test_http_direct_marks_failed_on_sha1_mismatch(
    tmp_path: Path,
) -> None:
    """Tampered (or truncated) upstream → sha1 mismatch → FAILED
    state + file removed so the importer never picks it up."""
    token = "tokTampered"
    body = b"ROM-BYTES-12"
    wrong_sha1 = "0000000000000000000000000000000000000000"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(
                size=len(body),
                checksums={"sha1": wrong_sha1},
            ),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-length": str(len(body))}
        )
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)

    status = await client.get_status(nid)
    assert status.state is DownloadState.FAILED
    snap = client._pending[nid]  # noqa: SLF001
    assert "checksum_mismatch" in (snap["error"] or "")
    assert "sha1" in (snap["error"] or "")
    # Bad bytes must not linger — the importer should never see them.
    assert not Path(snap["save_path"]).exists()


@respx.mock
async def test_http_direct_skips_verification_when_no_checksums(
    tmp_path: Path,
) -> None:
    """No checksums advertised → streamer just writes the file
    without computing digests. Stays COMPLETED, no error."""
    token = "tokNoChecksum"
    body = b"X" * 7
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200, json=_http_direct_resolve(size=len(body), checksums={})
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(200, content=body)
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    status = await client.get_status(nid)
    assert status.state is DownloadState.COMPLETED


@respx.mock
async def test_http_direct_case_insensitive_checksum_compare(
    tmp_path: Path,
) -> None:
    """no-intro DATs use uppercase hex; Edge Emulation lowercase.
    The comparison must accept both."""
    import hashlib

    token = "tokCase"
    body = b"DATA"
    sha1_upper = hashlib.sha1(body).hexdigest().upper()
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(
                size=len(body), checksums={"sha1": sha1_upper}
            ),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(200, content=body)
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    assert (await client.get_status(nid)).state is DownloadState.COMPLETED


@respx.mock
async def test_http_direct_unknown_algorithm_is_silently_skipped(
    tmp_path: Path,
) -> None:
    """A future Grabarr might add sha256 to the resolve response.
    An older Romarr should accept the download as long as the
    algorithms it CAN compute (sha1/md5/crc32) match — unknown
    algos are ignored, not treated as a missing-digest failure."""
    import hashlib

    token = "tokFuture"
    body = b"FUTURE"
    sha1 = hashlib.sha1(body).hexdigest()
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(
                size=len(body),
                checksums={"sha1": sha1, "sha256": "unknown-to-us"},
            ),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(200, content=body)
    )
    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    assert (await client.get_status(nid)).state is DownloadState.COMPLETED


# ---- slice 436 / content validation -------------------------------------


@respx.mock
async def test_http_direct_rejects_html_content_type_under_binary_extension(
    tmp_path: Path,
) -> None:
    """Slice 436 — Axekin / Anna's Archive / planet_emu sometimes
    return a 200 OK with ``Content-Type: text/html`` when the real
    upstream is rate-limited or hidden behind a CF challenge. Pre-
    slice the streamer wrote the HTML bytes to a ``.rar`` and the
    importer choked with "Not a RAR file"; this slice fails fast
    with an operator-actionable error."""
    token = "tokHtmlCt"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(filename="bogus.rar", size=10_000),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200,
            content=b"<!DOCTYPE html><html><head><title>CF</title></head></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    status = await client.get_status(nid)
    assert status.state is DownloadState.FAILED
    snap = client._pending[nid]  # noqa: SLF001
    assert "text/html" in (snap["error"] or "")
    assert "CF challenge" in (snap["error"] or "") or "rate-limit" in (
        snap["error"] or ""
    )
    # File must not linger.
    assert not Path(snap["save_path"]).exists()


@respx.mock
async def test_http_direct_rejects_html_body_with_binary_content_type(
    tmp_path: Path,
) -> None:
    """Some CF-protected sources lie on Content-Type
    (octet-stream) but still ship HTML in the body. Magic-byte
    sniff on the first chunk catches them."""
    token = "tokHtmlSniff"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(filename="bogus.zip", size=10_000),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200,
            content=b"<!doctype html><html><body>captcha</body></html>",
            headers={"content-type": "application/octet-stream"},
        )
    )

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    snap = client._pending[nid]  # noqa: SLF001
    assert snap["state"] == "FAILED"
    assert "HTML payload" in (snap["error"] or "")


@respx.mock
async def test_http_direct_accepts_text_content_for_non_binary_extension(
    tmp_path: Path,
) -> None:
    """A legitimate text/plain source (e.g., a .nfo or .txt) under
    a non-binary extension shouldn't trip the validation."""
    token = "tokText"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json=_http_direct_resolve(filename="readme.txt", size=20),
        )
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200,
            content=b"plain text readme",
            headers={"content-type": "text/plain"},
        )
    )
    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    assert (await client.get_status(nid)).state is DownloadState.COMPLETED


@respx.mock
async def test_http_direct_remove_cancels_in_flight_and_deletes(
    tmp_path: Path,
) -> None:
    token = "tokCancel"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200, json=_http_direct_resolve(size=1_000_000)
        )
    )

    # Slow stream: respx supports iterators of bytes for the content
    # — but the cleanest "in-flight" sim is a side_effect that sleeps.
    async def slow_stream(_req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return httpx.Response(200, content=b"X" * 1_000_000)

    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(side_effect=slow_stream)

    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    # Cancel immediately while the stream is sleeping.
    await client.remove(nid, delete_files=True)
    # The pending snap is gone — remove() is the explicit retract.
    assert nid not in client._pending  # noqa: SLF001
    # And the target path is unlinked.
    assert not (tmp_path / "romarr" / "sample.zip").exists()


# ---- torrent_magnet branch — re-route via NeedsMagnetClientError ---------


@respx.mock
async def test_torrent_magnet_raises_needs_magnet_client_error(
    tmp_path: Path,
) -> None:
    """When /resolve returns torrent_magnet, grabarr_direct raises
    :class:`NeedsMagnetClientError` carrying the magnet URI. The
    dispatcher catches this and re-routes to the operator's qBit
    client (covered in tests/search/test_dispatch.py).

    The pending snapshot is cleared before the raise so a subsequent
    ``get_status(native_id)`` correctly reports 'unknown' rather than
    leaving a phantom QUEUED entry the reconciler will keep polling."""
    from romarr.downloaders.errors import NeedsMagnetClientError

    token = "tokMagnet"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "torrent_magnet",
                "magnet_uri": "magnet:?xt=urn:btih:abc123",
                "filename": "Mario.z64",
                "filename_hint": "Mario.z64",
                "expected_size": 8_388_608,
                "headers": {},
                "checksums": {},
                "source": "vimm",
                "expires_at": "2026-05-13T00:00:00Z",
            },
        )
    )
    client = _client(tmp_path)
    with pytest.raises(NeedsMagnetClientError) as exc_info:
        await client.add_torrent(
            TorrentUrl(url=_torznab_url(token=token)),
            category="romarr",
            tags=[],
        )
    assert exc_info.value.magnet_uri == "magnet:?xt=urn:btih:abc123"
    # Snapshot cleared — no phantom QUEUED entry for the reconciler.
    assert f"grabarr-{token}" not in client._pending  # noqa: SLF001


# ---- resolve error paths -------------------------------------------------


@respx.mock
async def test_add_torrent_unknown_method_raises(tmp_path: Path) -> None:
    token = "tokWeird"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(
            200,
            json={"method": "warp_drive", "expires_at": "2026-05-13T00:00:00Z"},
        )
    )
    with pytest.raises(DownloaderError, match="unknown resolve method"):
        await _client(tmp_path).add_torrent(
            TorrentUrl(url=_torznab_url(token=token)),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_401_raises_auth(tmp_path: Path) -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokAuth"
    ).mock(return_value=httpx.Response(401, json={"code": "unauthenticated"}))
    with pytest.raises(AuthError):
        await _client(tmp_path).add_torrent(
            TorrentUrl(url=_torznab_url(token="tokAuth")),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_403_raises_auth(tmp_path: Path) -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokWrongProfile"
    ).mock(return_value=httpx.Response(403, json={"code": "forbidden"}))
    with pytest.raises(AuthError, match="different profile"):
        await _client(tmp_path).add_torrent(
            TorrentUrl(url=_torznab_url(token="tokWrongProfile")),
            category="romarr",
            tags=[],
        )


@respx.mock
async def test_add_torrent_expired_token_raises(tmp_path: Path) -> None:
    respx.get(
        f"{_BASE}/romarr/roms_all/api/v1/resolve/tokExpired"
    ).mock(return_value=httpx.Response(404, json={"code": "guid_not_found"}))
    with pytest.raises(DownloaderError, match="expired or unknown"):
        await _client(tmp_path).add_torrent(
            TorrentUrl(url=_torznab_url(token="tokExpired")),
            category="romarr",
            tags=[],
        )


# ---- lifecycle ----------------------------------------------------------


async def test_get_status_unknown_native_id_raises(tmp_path: Path) -> None:
    with pytest.raises(DownloaderError, match="unknown native_id"):
        await _client(tmp_path).get_status("grabarr-never-added")


async def test_remove_is_idempotent_on_missing_entry(tmp_path: Path) -> None:
    await _client(tmp_path).remove(
        "grabarr-never-added", delete_files=False
    )  # no raise


@respx.mock
async def test_list_managed_downloads_returns_completed_entries(
    tmp_path: Path,
) -> None:
    token = "tokDone"
    respx.get(f"{_BASE}/romarr/roms_all/api/v1/resolve/{token}").mock(
        return_value=httpx.Response(200, json=_http_direct_resolve(size=3))
    )
    respx.get(f"{_FILE_HOST}/files/sample.zip").mock(
        return_value=httpx.Response(
            200, content=b"xyz", headers={"content-length": "3"}
        )
    )
    client = _client(tmp_path)
    nid = await client.add_torrent(
        TorrentUrl(url=_torznab_url(token=token)),
        category="romarr",
        tags=[],
    )
    await client.wait_for_task(nid)
    managed = await client.list_managed_downloads()
    assert len(managed) == 1
    entry = managed[0]
    assert entry.client_id == 42
    assert entry.client_native_id == nid
    assert entry.save_path == str(tmp_path / "romarr" / "sample.zip")
    assert entry.imported is False


async def test_list_managed_downloads_excludes_in_flight(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    # Inject a DOWNLOADING entry manually — no completed file, no
    # ManagedDownload row.
    client._pending["grabarr-flight"] = {  # noqa: SLF001
        "method": "http_direct",
        "state": "DOWNLOADING",
        "filename": "x.bin",
        "save_path": str(tmp_path / "x.bin"),
    }
    assert await client.list_managed_downloads() == []


async def test_ensure_category_is_a_noop(tmp_path: Path) -> None:
    await _client(tmp_path).ensure_category()  # no raise


async def test_set_imported_tag_is_a_noop(tmp_path: Path) -> None:
    await _client(tmp_path).set_imported_tag("any-id")  # no raise


async def test_add_nzb_rejects_usenet(tmp_path: Path) -> None:
    from romarr.downloaders.types import NzbUrl

    with pytest.raises(ValueError, match="does not accept Usenet"):
        await _client(tmp_path).add_nzb(
            NzbUrl(url="http://example.test/x.nzb"),
            category="romarr",
        )
