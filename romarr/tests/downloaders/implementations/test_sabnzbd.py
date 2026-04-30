"""SABnzbd implementation tests (T033-T038)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from romarr.downloaders.errors import AuthError, CategoryWarning
from romarr.downloaders.implementations.sabnzbd import SabnzbdClient
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    NzbBytes,
    NzbUrl,
)


def _client(api_key: str = "valid-key") -> SabnzbdClient:
    return SabnzbdClient(
        client_id=1,
        name="SAB",
        host="sab.test",
        port=8080,
        api_key=api_key,
        category_default="romarr",
    )


def test_class_metadata() -> None:
    assert SabnzbdClient.client_type is ClientType.SABNZBD
    assert SabnzbdClient.supports_torrents is False
    assert SabnzbdClient.supports_usenet is True
    assert SabnzbdClient.available is True


def test_base_url_assembly() -> None:
    client = SabnzbdClient(
        client_id=1,
        name="SAB",
        host="sab.test",
        port=9090,
        api_key="k",
        use_ssl=True,
        url_base="/sabnzbd",
    )
    assert client.base_url == "https://sab.test:9090/sabnzbd/api"


# ---------------------------------------------------------------------------
# T033 — addurl
# ---------------------------------------------------------------------------


@respx.mock
async def test_addurl_uses_query_params(sab_fixture: Callable[[str], bytes]) -> None:
    route = respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(200, content=sab_fixture("addurl_ok.json"))
    )
    client = _client()
    nzo_id = await client.add_nzb(
        NzbUrl(url="http://example.test/file.nzb"),  # type: ignore[arg-type]
        category="romarr",
    )

    assert nzo_id == "SABnzbd_nzo_abc123"
    assert route.called
    request = route.calls.last.request
    qs = dict(request.url.params.multi_items())
    assert qs["mode"] == "addurl"
    assert qs["apikey"] == "valid-key"
    assert qs["output"] == "json"
    assert qs["name"] == "http://example.test/file.nzb"
    assert qs["cat"] == "romarr"


# ---------------------------------------------------------------------------
# T034 — addfile multipart
# ---------------------------------------------------------------------------


@respx.mock
async def test_addfile_uploads_multipart(sab_fixture: Callable[[str], bytes]) -> None:
    route = respx.post("http://sab.test:8080/api").mock(
        return_value=httpx.Response(200, content=sab_fixture("addfile_ok.json"))
    )
    client = _client()
    nzo_id = await client.add_nzb(NzbBytes(data=b"<nzb>...</nzb>"), category="romarr")

    assert nzo_id == "SABnzbd_nzo_xyz789"
    assert route.called
    request = route.calls.last.request
    qs = dict(request.url.params.multi_items())
    assert qs["mode"] == "addfile"
    assert qs["cat"] == "romarr"
    body = request.content
    # multipart body contains the literal filename + payload bytes
    assert b'name="nzbfile"' in body
    assert b"<nzb>...</nzb>" in body


# ---------------------------------------------------------------------------
# T035 — queue status (Usenet has no peers)
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_status_from_queue(sab_fixture: Callable[[str], bytes]) -> None:
    respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(
            200, content=sab_fixture("queue_downloading.json")
        )
    )
    client = _client()
    status = await client.get_status("SABnzbd_nzo_abc123")

    assert status.client_id == 1
    assert status.client_native_id == "SABnzbd_nzo_abc123"
    assert status.state is DownloadState.DOWNLOADING
    assert 0.74 < status.progress < 0.76  # 75%
    assert status.eta_seconds == 90  # 0:01:30
    assert status.download_rate_bps == 5_300_000  # 5300 kb/s -> 5.3M b/s
    # Usenet: no peers/seeders/upload rate
    assert status.seeders is None
    assert status.peers is None
    assert status.upload_rate_bps is None


# ---------------------------------------------------------------------------
# T036 — history completed paths
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_status_falls_back_to_history(
    sab_fixture: Callable[[str], bytes],
) -> None:
    """When queue doesn't carry the nzo_id, history is queried.

    SAB serves both modes off the same /api endpoint differentiated by
    the ?mode= query param; respx routes by URL only, so we side-effect
    the response based on the inbound mode.
    """
    queue_empty = b'{"queue": {"slots": []}}'
    history_body = sab_fixture("history_completed.json")

    def _route(request: httpx.Request) -> httpx.Response:
        mode = request.url.params.get("mode")
        if mode == "queue":
            return httpx.Response(200, content=queue_empty)
        if mode == "history":
            return httpx.Response(200, content=history_body)
        return httpx.Response(404)  # pragma: no cover

    respx.get("http://sab.test:8080/api").mock(side_effect=_route)
    client = _client()
    status = await client.get_status("SABnzbd_nzo_abc123")

    assert status.state is DownloadState.COMPLETED
    assert status.progress == 1.0
    assert status.completed_paths == [
        "/downloads/complete/romarr/Sonic.the.Hedgehog.Mega.Drive.[U]"
    ]


# ---------------------------------------------------------------------------
# T037 — invalid api key → AuthError
# ---------------------------------------------------------------------------


@respx.mock
async def test_invalid_apikey_raises_auth(
    sab_fixture: Callable[[str], bytes],
) -> None:
    respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(
            200, content=sab_fixture("invalid_apikey.json")
        )
    )
    client = _client(api_key="bad-key")
    with pytest.raises(AuthError, match="API Key Incorrect"):
        await client.test_connection()


# ---------------------------------------------------------------------------
# T038 — missing category → CategoryWarning (FR-011)
# ---------------------------------------------------------------------------


@respx.mock
async def test_missing_category_warns(
    sab_fixture: Callable[[str], bytes],
) -> None:
    respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(
            200, content=sab_fixture("get_cats_missing_romarr.json")
        )
    )
    client = _client()
    with pytest.raises(CategoryWarning, match="romarr"):
        await client.ensure_category()


@respx.mock
async def test_present_category_no_warning(
    sab_fixture: Callable[[str], bytes],
) -> None:
    respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(
            200, content=sab_fixture("get_cats_with_romarr.json")
        )
    )
    client = _client()
    await client.ensure_category()  # no exception


# ---------------------------------------------------------------------------
# Version probe / test_connection
# ---------------------------------------------------------------------------


@respx.mock
async def test_test_connection_returns_version(
    sab_fixture: Callable[[str], bytes],
) -> None:
    respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(200, content=sab_fixture("version.json"))
    )
    client = _client()
    version = await client.test_connection()
    assert "4.3.2" in version


# ---------------------------------------------------------------------------
# Remove — delete with files
# ---------------------------------------------------------------------------


@respx.mock
async def test_remove_with_delete_files() -> None:
    route = respx.get("http://sab.test:8080/api").mock(
        return_value=httpx.Response(200, content=b'{"status": true}')
    )
    client = _client()
    await client.remove("nzo-1", delete_files=True)
    qs = dict(route.calls.last.request.url.params.multi_items())
    assert qs["mode"] == "queue"
    assert qs["name"] == "delete"
    assert qs["value"] == "nzo-1"
    assert qs["del_files"] == "1"


# ---------------------------------------------------------------------------
# add_torrent rejected
# ---------------------------------------------------------------------------


async def test_add_torrent_not_implemented() -> None:
    from romarr.downloaders.types import TorrentMagnet

    client = _client()
    with pytest.raises(NotImplementedError, match="not handle torrents"):
        await client.add_torrent(
            TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:abc"),
            category="romarr",
            tags=["romarr"],
        )


async def test_set_imported_tag_is_noop() -> None:
    """SAB has no tag concept; the method is a documented no-op."""
    client = _client()
    assert await client.set_imported_tag("nzo-1") is None
