"""Dispatch integration tests (T074-T076)."""

from __future__ import annotations

from typing import Any

import pytest

from romarr.downloaders.errors import (
    AuthError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.routing import RoutingCandidate
from romarr.search.dispatch import (
    DispatchStatus,
    dispatch_winner,
)
from romarr.search.types import (
    Candidate,
    ScoreBreakdown,
    ScoreContribution,
)


def _candidate(
    *,
    download_url: str = "https://idx.test/file.torrent",
    indexer_id: int = 1,
) -> Candidate:
    return Candidate(
        indexer_id=indexer_id,
        indexer_guid=f"g-{indexer_id}",
        title="Sonic the Hedgehog (USA)",
        download_url=download_url,
        size_bytes=1_000_000,
        seeders=10,
        matched_release_id=10,
        matched_game_id=1,
        score_breakdown=ScoreBreakdown(
            total=120,
            contributions=[ScoreContribution(source="region", name="USA", value=120)],
        ),
        rejection=None,
        would_auto_reject=False,
    )


class _FakeDownloadClient:
    """Stand-in for :class:`DownloadClient` used in the dispatch tests."""

    def __init__(
        self,
        *,
        client_id: int,
        raise_on_add: BaseException | None = None,
    ) -> None:
        self.client_id = client_id
        self.add_torrent_calls: list[Any] = []
        self.add_nzb_calls: list[Any] = []
        self.closed = False
        self._raise_on_add = raise_on_add

    async def add_torrent(
        self,
        source: Any,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        if self._raise_on_add is not None:
            raise self._raise_on_add
        self.add_torrent_calls.append(
            {"source": source, "category": category, "tags": tags}
        )
        return "info-hash-abc"

    async def add_nzb(self, source: Any, *, category: str) -> str:
        if self._raise_on_add is not None:
            raise self._raise_on_add
        self.add_nzb_calls.append({"source": source, "category": category})
        return "nzo-1"

    async def aclose(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# T074 — dispatch routes via spec-005's route_release + calls add_torrent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_via_route_release() -> None:
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]
    fake = _FakeDownloadClient(client_id=1)

    async def factory(client_id: int) -> _FakeDownloadClient:
        assert client_id == 1
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.GRABBED
    assert outcome.client_id == 1
    assert outcome.client_native_id == "info-hash-abc"
    # aclose() is not part of the DownloadClient ABC
    assert len(fake.add_torrent_calls) == 1


# ---------------------------------------------------------------------------
# T075 — routing failure recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_eligible_client_outcome() -> None:
    """No torrent-capable clients → dispatch returns NO_ELIGIBLE_CLIENT."""
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=False, enable_for_usenet=True,
        )
    ]

    async def factory(client_id: int) -> _FakeDownloadClient:
        raise AssertionError("client factory called when no eligible client")

    outcome = await dispatch_winner(
        candidate=_candidate(),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.NO_ELIGIBLE_CLIENT
    assert outcome.client_id is None
    assert outcome.reason


# ---------------------------------------------------------------------------
# T076 — transient connection error → pending_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_connection_error_is_pending_retry() -> None:
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]
    fake = _FakeDownloadClient(
        client_id=1,
        raise_on_add=DownloaderConnError("connection refused"),
    )

    async def factory(client_id: int) -> _FakeDownloadClient:
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.PENDING_RETRY
    assert "transient" in (outcome.reason or "")
    # aclose() is not part of the DownloadClient ABC


# ---------------------------------------------------------------------------
# Non-transient AuthError → FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_is_failed() -> None:
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]
    fake = _FakeDownloadClient(
        client_id=1, raise_on_add=AuthError("bad creds")
    )

    async def factory(client_id: int) -> _FakeDownloadClient:
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.FAILED
    assert "non-transient" in (outcome.reason or "")


# ---------------------------------------------------------------------------
# .nzb URL → SourceKind.USENET path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nzb_url_dispatched_to_usenet_client() -> None:
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=False, enable_for_usenet=True,
        )
    ]
    fake = _FakeDownloadClient(client_id=1)

    async def factory(client_id: int) -> _FakeDownloadClient:
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(download_url="https://idx.test/file.nzb"),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.GRABBED
    assert len(fake.add_nzb_calls) == 1
    assert fake.add_torrent_calls == []


# ---------------------------------------------------------------------------
# Magnet URL detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_magnet_url_dispatched_to_torrent_client() -> None:
    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]
    fake = _FakeDownloadClient(client_id=1)

    async def factory(client_id: int) -> _FakeDownloadClient:
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(download_url="magnet:?xt=urn:btih:abc"),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.GRABBED
    assert len(fake.add_torrent_calls) == 1


# ---------------------------------------------------------------------------
# _resolve_torrent_source — 302→magnet, bytes proxy, and fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_302_magnet_returns_torrent_magnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grabarr's typical response: 302 Found with Location=magnet:xxx.
    The resolver must extract the magnet URI so the client gets a
    TorrentMagnet (bypasses the client's HTTP-follow-that-can't-do-magnet)."""
    import httpx

    from romarr.downloaders.types import TorrentMagnet
    from romarr.search.dispatch import _resolve_torrent_source

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "magnet:?xt=urn:btih:abc123&dn=Test"},
        )

    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        orig_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    src = await _resolve_torrent_source("http://example.test/x.torrent")
    assert isinstance(src, TorrentMagnet)
    assert src.magnet_uri.startswith("magnet:?xt=urn:btih:abc123")


@pytest.mark.asyncio
async def test_resolve_200_torrent_body_returns_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real .torrent (bencoded dict starts with 'd') → push bytes."""
    import httpx

    from romarr.downloaders.types import TorrentBytes
    from romarr.search.dispatch import _resolve_torrent_source

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"d5:filesle")

    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        orig_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    src = await _resolve_torrent_source("http://example.test/x.torrent")
    assert isinstance(src, TorrentBytes)
    assert src.data == b"d5:filesle"


@pytest.mark.asyncio
async def test_resolve_network_error_falls_back_to_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any exception during fetch → fall back to TorrentUrl so the
    client tries the URL directly (matches pre-proxy behaviour)."""
    import httpx

    from romarr.downloaders.types import TorrentUrl
    from romarr.search.dispatch import _resolve_torrent_source

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS fail")

    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        orig_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    src = await _resolve_torrent_source("http://example.test/x.torrent")
    assert isinstance(src, TorrentUrl)
    assert str(src.url).rstrip("/") == "http://example.test/x.torrent"


@pytest.mark.asyncio
async def test_client_preserves_source_url_skips_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client with ``preserves_source_url = True`` (e.g. grabarr_direct)
    must receive the ORIGINAL http(s) URL, not a magnet/bytes variant —
    even when the URL would 302→magnet. The resolver must NOT run."""
    from romarr.downloaders.types import TorrentUrl
    from romarr.search import dispatch as dispatch_mod

    called = False

    async def spy_resolve(url: str):
        nonlocal called
        called = True
        raise AssertionError("_resolve_torrent_source must not be called")

    monkeypatch.setattr(dispatch_mod, "_resolve_torrent_source", spy_resolve)

    fake = _FakeDownloadClient(client_id=1)
    fake.preserves_source_url = True  # simulate grabarr_direct

    candidates = [
        RoutingCandidate(
            id=1, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]

    async def factory(client_id: int) -> _FakeDownloadClient:
        return fake

    outcome = await dispatch_winner(
        candidate=_candidate(download_url="https://grabarr.test/download/tok.torrent"),
        candidates=candidates,
        client_factory=factory,
    )
    assert outcome.status is DispatchStatus.GRABBED
    assert not called
    assert len(fake.add_torrent_calls) == 1
    src = fake.add_torrent_calls[0]["source"]
    assert isinstance(src, TorrentUrl)
    assert str(src.url) == "https://grabarr.test/download/tok.torrent"


@pytest.mark.asyncio
async def test_resolve_200_html_error_page_falls_back_to_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indexer returned 200 but the body isn't a bencoded torrent
    (typical HTML error page) → fall back to URL."""
    import httpx

    from romarr.downloaders.types import TorrentUrl
    from romarr.search.dispatch import _resolve_torrent_source

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>error</html>")

    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        orig_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    src = await _resolve_torrent_source("http://example.test/x.torrent")
    assert isinstance(src, TorrentUrl)
