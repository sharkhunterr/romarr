"""qBittorrent implementation tests (T024-T031 + CL001/CL003/CL006)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from romarr.downloaders.errors import (
    AuthError,
    VersionError,
)
from romarr.downloaders.implementations.qbittorrent import (
    MIN_WEBAPI_VERSION,
    QBittorrentClient,
)
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    NzbUrl,
    TorrentBytes,
    TorrentMagnet,
    TorrentUrl,
)

_FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures/qbittorrent"
_BASE = "http://qbit.test:8080/api/v2"


def _client(*, username: str = "admin", password: str = "adminpass") -> QBittorrentClient:
    return QBittorrentClient(
        client_id=1,
        name="qBit",
        host="qbit.test",
        port=8080,
        username=username,
        password=password,
        category_default="romarr",
    )


def _login_ok() -> httpx.Response:
    return httpx.Response(
        200, content=b"Ok.", headers={"Set-Cookie": "SID=abc; HttpOnly"}
    )


def _qbit_fixture(name: str) -> bytes:
    path = _FIXTURES / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Class metadata
# ---------------------------------------------------------------------------


def test_class_metadata() -> None:
    assert QBittorrentClient.client_type is ClientType.QBITTORRENT
    assert QBittorrentClient.supports_torrents is True
    assert QBittorrentClient.supports_usenet is False
    assert QBittorrentClient.available is True


def test_base_url_assembly() -> None:
    client = QBittorrentClient(
        client_id=1,
        name="qBit",
        host="qbit.test",
        port=9090,
        username="u",
        password="p",
        use_ssl=True,
        url_base="/qbit",
    )
    assert client.base_url == "https://qbit.test:9090/qbit/api/v2"


# ---------------------------------------------------------------------------
# T024 — auth login
# ---------------------------------------------------------------------------


@respx.mock
async def test_login_happy_path() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(200, content=b"2.9.3")
    )
    respx.get(f"{_BASE}/app/version").mock(
        return_value=httpx.Response(200, content=b"v4.6.5")
    )
    version = await _client().test_connection()
    assert "qBittorrent" in version
    assert "v4.6.5" in version


@respx.mock
async def test_login_rejected_raises_auth() -> None:
    respx.post(f"{_BASE}/auth/login").mock(
        return_value=httpx.Response(200, content=b"Fails.")
    )
    with pytest.raises(AuthError):
        await _client().test_connection()


@respx.mock
async def test_login_403_raises_auth() -> None:
    respx.post(f"{_BASE}/auth/login").mock(
        return_value=httpx.Response(403, content=b"banned")
    )
    with pytest.raises(AuthError):
        await _client().test_connection()


@respx.mock
async def test_login_accepts_qbit5_qbt_sid_cookie() -> None:
    """qBittorrent 5.x renames the session cookie from ``SID`` to
    ``QBT_SID_<internal-port>`` (e.g. ``QBT_SID_8080``) and returns
    204 instead of ``200 Ok.`` on login. Both must be recognised as
    a successful session — no probe should be needed."""
    respx.post(f"{_BASE}/auth/login").mock(
        return_value=httpx.Response(
            204,
            headers={
                "Set-Cookie": (
                    "QBT_SID_8080=fnm+XfAfqdB92RorMJ3ZfK+RwHmaZCDy; "
                    "HttpOnly; path=/"
                )
            },
        )
    )
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(200, content=b"2.11.4")
    )
    respx.get(f"{_BASE}/app/version").mock(
        return_value=httpx.Response(200, content=b"v5.2.3")
    )
    version = await _client().test_connection()
    assert "qBittorrent" in version
    assert "v5.2.3" in version


@respx.mock
async def test_login_no_cookie_but_probe_succeeds_is_treated_as_authed() -> None:
    """qBit with AuthSubnetWhitelist covering Romarr returns 200 (or 204)
    without a Set-Cookie because it bypasses auth per-request. Romarr
    used to reject this as ``did not return an SID cookie`` even though
    subsequent API calls work fine. The probe now confirms auth is
    effectively in place before failing."""
    respx.post(f"{_BASE}/auth/login").mock(
        return_value=httpx.Response(204)  # no body, no cookie
    )
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(200, content=b"2.9.3")
    )
    respx.get(f"{_BASE}/app/version").mock(
        return_value=httpx.Response(200, content=b"v4.6.5")
    )
    version = await _client().test_connection()
    assert "qBittorrent" in version
    assert "v4.6.5" in version


@respx.mock
async def test_login_no_cookie_and_probe_401_raises_auth() -> None:
    """Empty login response + probe returns 401 = the creds really are
    wrong (qBit lied with a 2xx on the login itself)."""
    respx.post(f"{_BASE}/auth/login").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{_BASE}/app/version").mock(
        return_value=httpx.Response(401, content=b"")
    )
    with pytest.raises(AuthError):
        await _client().test_connection()


# ---------------------------------------------------------------------------
# CL003 / FR-005a — minimum webapi version
# ---------------------------------------------------------------------------


@respx.mock
async def test_too_old_webapi_version_raises_version_error() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(200, content=b"2.7.0")
    )
    with pytest.raises(VersionError, match=r"upgrade qBittorrent to 4\.4\.0"):
        await _client().test_connection()


@respx.mock
async def test_exact_minimum_webapi_version_accepted() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(
            200,
            content=".".join(str(p) for p in MIN_WEBAPI_VERSION).encode(),
        )
    )
    respx.get(f"{_BASE}/app/version").mock(
        return_value=httpx.Response(200, content=b"v4.4.0")
    )
    version = await _client().test_connection()
    assert "v4.4.0" in version


@respx.mock
async def test_unparseable_webapi_version_raises_version_error() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/app/webapiVersion").mock(
        return_value=httpx.Response(200, content=b"not-a-version")
    )
    with pytest.raises(VersionError):
        await _client().test_connection()


# ---------------------------------------------------------------------------
# T025 — ensure_category creates missing category
# ---------------------------------------------------------------------------


@respx.mock
async def test_ensure_category_creates_when_missing() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/torrents/categories").mock(
        return_value=httpx.Response(200, content=_qbit_fixture("categories_empty.json"))
    )
    create = respx.post(f"{_BASE}/torrents/createCategory").mock(
        return_value=httpx.Response(200)
    )
    await _client().ensure_category()
    assert create.called
    body = dict(httpx.QueryParams(create.calls.last.request.content.decode()))
    assert body["category"] == "romarr"


@respx.mock
async def test_ensure_category_skips_when_present() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/torrents/categories").mock(
        return_value=httpx.Response(
            200, content=_qbit_fixture("categories_with_romarr.json")
        )
    )
    create = respx.post(f"{_BASE}/torrents/createCategory")
    await _client().ensure_category()
    assert not create.called


# ---------------------------------------------------------------------------
# T026 — add_torrent magnet with tags
# ---------------------------------------------------------------------------


@respx.mock
async def test_add_torrent_magnet_carries_category_tags_savepath() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    # Pre-add lookup: nothing exists yet.
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(200, content=b"[]")
    )
    add_route = respx.post(f"{_BASE}/torrents/add").mock(
        return_value=httpx.Response(200, content=b"Ok.")
    )

    magnet_hash = "abc123def456abc123def456abc123def456abcd"
    nzo = await _client().add_torrent(
        TorrentMagnet(magnet_uri=f"magnet:?xt=urn:btih:{magnet_hash}&dn=Sonic"),
        category="romarr",
        tags=["romarr", "romarr-megadrive"],
        save_path="/downloads/incomplete/romarr",
    )
    assert nzo == magnet_hash.lower()
    assert add_route.called
    body = dict(httpx.QueryParams(add_route.calls.last.request.content.decode()))
    assert body["category"] == "romarr"
    assert body["tags"] == "romarr,romarr-megadrive"
    assert body["savepath"] == "/downloads/incomplete/romarr"
    assert body["urls"].startswith("magnet:?")


# ---------------------------------------------------------------------------
# CL001 / CL006 — idempotent on existing info-hash
# ---------------------------------------------------------------------------


@respx.mock
async def test_add_torrent_idempotent_when_info_hash_exists() -> None:
    """When the magnet's info-hash is already in qBit, return existing
    hash, additively merge tags, do NOT call /torrents/add, leave
    category alone (FR-004a / CL001).
    """
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())

    magnet_hash = "abc123def456abc123def456abc123def456abcd"
    existing = [
        {
            "hash": magnet_hash,
            "name": "Sonic",
            "category": "user-set-this",  # MUST stay untouched
            "tags": "user-tag, romarr",
        }
    ]
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(200, json=existing)
    )
    add_tags = respx.post(f"{_BASE}/torrents/addTags").mock(
        return_value=httpx.Response(200)
    )
    add_route = respx.post(f"{_BASE}/torrents/add")  # MUST NOT be called

    nzo = await _client().add_torrent(
        TorrentMagnet(magnet_uri=f"magnet:?xt=urn:btih:{magnet_hash}"),
        category="romarr",
        tags=["romarr", "romarr-megadrive"],
    )
    assert nzo == magnet_hash.lower()
    assert add_tags.called
    body = dict(httpx.QueryParams(add_tags.calls.last.request.content.decode()))
    assert body["hashes"] == magnet_hash.lower()
    assert "romarr" in body["tags"]
    assert "romarr-megadrive" in body["tags"]
    assert not add_route.called


@respx.mock
async def test_add_torrent_idempotent_no_tags_skips_addtags_call() -> None:
    """If the caller passes an empty tag list, don't issue a noisy
    addTags call (still idempotent return)."""
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    magnet_hash = "abc123def456abc123def456abc123def456abcd"
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(200, json=[{"hash": magnet_hash, "name": "x"}])
    )
    add_tags = respx.post(f"{_BASE}/torrents/addTags")
    nzo = await _client().add_torrent(
        TorrentMagnet(magnet_uri=f"magnet:?xt=urn:btih:{magnet_hash}"),
        category="romarr",
        tags=[],
    )
    assert nzo == magnet_hash.lower()
    assert not add_tags.called


# ---------------------------------------------------------------------------
# add_torrent with .torrent URL or bytes — falls back to discover-by-list
# ---------------------------------------------------------------------------


@respx.mock
async def test_add_torrent_url_discovers_hash_post_add() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.post(f"{_BASE}/torrents/add").mock(return_value=httpx.Response(200))
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(
            200, json=[{"hash": "DEADBEEF" * 5, "name": "x"}]
        )
    )
    # The pre-resolve probe (slice 359) performs a no-redirect
    # GET on the URL before handing it to qBit. Mock it to a 200
    # with a non-torrent content type so the resolver returns
    # None and falls back to the legacy "let qBit fetch the URL
    # itself" path this test asserts on.
    respx.get("https://example.test/x.torrent").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b""
        )
    )
    nzo = await _client().add_torrent(
        TorrentUrl(url="https://example.test/x.torrent"),  # type: ignore[arg-type]
        category="romarr",
        tags=["romarr"],
    )
    assert nzo == ("deadbeef" * 5).lower()


@respx.mock
async def test_add_torrent_url_redirecting_to_magnet_uses_magnet_path() -> None:
    """Slice 359 — Prowlarr-style 301 to ``magnet:?xt=…`` is folded
    into a TorrentMagnet source so qBit gets a vocabulary it
    understands. The post-add hash discovery is skipped because
    the magnet's btih short-circuits to the canonical hash."""
    info_hash = "abcdef0123456789abcdef0123456789abcdef01"
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.post(f"{_BASE}/torrents/add").mock(return_value=httpx.Response(200))
    # No /torrents/info call should fire — the magnet hash takes over.
    respx.get(
        "https://prowlarr.test/12/download?apikey=K&link=opaque",
    ).mock(
        return_value=httpx.Response(
            301,
            headers={"location": f"magnet:?xt=urn:btih:{info_hash}&dn=demo"},
        )
    )
    # Idempotency check for the magnet path also calls
    # /torrents/info to look up an existing match — return [] so
    # the add proceeds.
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(200, json=[])
    )
    nzo = await _client().add_torrent(
        TorrentUrl(  # type: ignore[arg-type]
            url="https://prowlarr.test/12/download?apikey=K&link=opaque",
        ),
        category="romarr",
        tags=["romarr"],
    )
    assert nzo == info_hash


@respx.mock
async def test_add_torrent_bytes_uploads_multipart() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    add_route = respx.post(f"{_BASE}/torrents/add").mock(
        return_value=httpx.Response(200)
    )
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(
            200, json=[{"hash": "FEED" * 10, "name": "x"}]
        )
    )
    await _client().add_torrent(
        TorrentBytes(data=b"d8:announce..."),
        category="romarr",
        tags=["romarr"],
    )
    assert add_route.called
    assert b'name="torrents"' in add_route.calls.last.request.content
    assert b"d8:announce..." in add_route.calls.last.request.content


# ---------------------------------------------------------------------------
# T027 — get_status canonical shape
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_status_canonical_shape() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(
            200, content=_qbit_fixture("torrents_info_downloading.json")
        )
    )
    respx.get(f"{_BASE}/torrents/files").mock(
        return_value=httpx.Response(200, content=b"[]")
    )

    status = await _client().get_status(
        "abc123def456abc123def456abc123def456abcd"
    )
    assert status.client_id == 1
    assert status.state is DownloadState.DOWNLOADING
    assert status.progress == pytest.approx(0.42)
    assert status.eta_seconds == 360
    assert status.seeders == 8
    assert status.peers == 3
    assert status.download_rate_bps == 5_242_880
    assert status.upload_rate_bps == 102_400
    assert status.save_path == "/downloads/incomplete/romarr"
    assert status.completed_paths == []  # not done


# ---------------------------------------------------------------------------
# T028 — state mapping table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("qbit_state", "expected"),
    [
        ("downloading", DownloadState.DOWNLOADING),
        ("forcedDL", DownloadState.DOWNLOADING),
        ("metaDL", DownloadState.DOWNLOADING),
        ("stalledDL", DownloadState.STALLED),
        ("uploading", DownloadState.SEEDING),
        ("forcedUP", DownloadState.SEEDING),
        ("stalledUP", DownloadState.SEEDING),
        ("pausedDL", DownloadState.PAUSED),
        ("pausedUP", DownloadState.COMPLETED),
        ("error", DownloadState.FAILED),
        ("missingFiles", DownloadState.FAILED),
        ("queuedDL", DownloadState.QUEUED),
        ("queuedUP", DownloadState.QUEUED),
    ],
)
@respx.mock
async def test_state_mapping(qbit_state: str, expected: DownloadState) -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    payload = [
        {
            "hash": "abc",
            "name": "x",
            "state": qbit_state,
            "progress": 0.5,
            "eta": 0,
            "save_path": "/x",
        }
    ]
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(200, json=payload)
    )
    respx.get(f"{_BASE}/torrents/files").mock(
        return_value=httpx.Response(200, content=b"[]")
    )
    status = await _client().get_status("abc")
    assert status.state is expected


# ---------------------------------------------------------------------------
# T029 — completed file paths
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_completed_files() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    respx.get(f"{_BASE}/torrents/info").mock(
        return_value=httpx.Response(
            200, content=_qbit_fixture("torrents_info_completed.json")
        )
    )
    respx.get(f"{_BASE}/torrents/files").mock(
        return_value=httpx.Response(
            200, content=_qbit_fixture("torrents_files.json")
        )
    )
    status = await _client().get_status(
        "abc123def456abc123def456abc123def456abcd"
    )
    assert status.state is DownloadState.SEEDING
    assert status.progress == 1.0
    assert sorted(status.completed_paths) == [
        "/downloads/complete/romarr/Sonic.the.Hedgehog.Mega.Drive.[U].zip",
        "/downloads/complete/romarr/readme.txt",
    ]


# ---------------------------------------------------------------------------
# T030 — set_imported_tag
# ---------------------------------------------------------------------------


@respx.mock
async def test_set_imported_tag_calls_addtags() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    add_tags = respx.post(f"{_BASE}/torrents/addTags").mock(
        return_value=httpx.Response(200)
    )
    await _client().set_imported_tag(
        "abc123def456abc123def456abc123def456abcd"
    )
    assert add_tags.called
    body = dict(httpx.QueryParams(add_tags.calls.last.request.content.decode()))
    assert body["hashes"] == "abc123def456abc123def456abc123def456abcd"
    assert body["tags"] == "romarr-imported"


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@respx.mock
async def test_remove_with_delete_files() -> None:
    respx.post(f"{_BASE}/auth/login").mock(return_value=_login_ok())
    delete = respx.post(f"{_BASE}/torrents/delete").mock(
        return_value=httpx.Response(200)
    )
    await _client().remove(
        "abc123def456abc123def456abc123def456abcd", delete_files=True
    )
    body = dict(httpx.QueryParams(delete.calls.last.request.content.decode()))
    assert body["hashes"] == "abc123def456abc123def456abc123def456abcd"
    assert body["deleteFiles"] == "true"


# ---------------------------------------------------------------------------
# add_nzb rejected
# ---------------------------------------------------------------------------


async def test_add_nzb_not_implemented() -> None:
    client = _client()
    with pytest.raises(NotImplementedError, match="not handle NZB"):
        await client.add_nzb(
            NzbUrl(url="https://x.test/file.nzb"),  # type: ignore[arg-type]
            category="romarr",
        )


# ---------------------------------------------------------------------------
# T031 — async-native (no asyncio.to_thread needed since httpx is async)
# ---------------------------------------------------------------------------


def test_methods_are_async_native() -> None:
    """Direct httpx is async-native; no asyncio.to_thread plumbing needed.

    Smoke-checked by walking the module AST and confirming that no
    call expression resolves to ``asyncio.to_thread`` or
    ``asyncio.run_in_executor``. Doc-strings are skipped automatically.
    """
    import ast

    import romarr.downloaders.implementations.qbittorrent as qb_module

    tree = ast.parse(Path(qb_module.__file__).read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "asyncio"
            and node.attr in {"to_thread", "run_in_executor"}
        ):
            pytest.fail(
                f"unexpected asyncio.{node.attr} in qbittorrent.py "
                "— direct httpx is async-native; no thread offload needed"
            )


# ---------------------------------------------------------------------------
# Magnet info-hash extraction edges
# ---------------------------------------------------------------------------


def test_magnet_hash_extraction(
    sab_fixture: Callable[[str], bytes] | None = None,
) -> None:
    """Pure helper — verify the regex handles SHA-1 hex (40 chars).

    Base32 magnets (32 chars) intentionally fall through to the
    discover-by-list path, so the helper returns None for them.
    """
    from romarr.downloaders.implementations.qbittorrent import (
        _maybe_extract_magnet_hash,
    )

    sha1 = "abc123def456abc123def456abc123def456abcd"
    assert (
        _maybe_extract_magnet_hash(
            TorrentMagnet(magnet_uri=f"magnet:?xt=urn:btih:{sha1}&dn=foo")
        )
        == sha1.lower()
    )
    # Base32 (32 chars) → None (qBit handles dedup natively)
    base32 = "MFRGGZDFMZTWQ2LKMFTGS3DPMNQXM2LO"
    assert (
        _maybe_extract_magnet_hash(
            TorrentMagnet(magnet_uri=f"magnet:?xt=urn:btih:{base32}")
        )
        is None
    )
    # No xt param → None
    assert (
        _maybe_extract_magnet_hash(
            TorrentMagnet(magnet_uri="magnet:?dn=just-a-name")
        )
        is None
    )
    # Non-magnet sources → None
    assert _maybe_extract_magnet_hash(TorrentBytes(data=b"x")) is None
