"""Pre-resolve dispatcher helper for grabarr indexers — slice 426 / R2e.

Covers:

- URL parsing (Torznab download URL on the indexer's base host).
- Passthrough for newznab/torznab indexers.
- http_direct path leaves the candidate + pin intact.
- torrent_magnet path rewrites ``download_url`` to the magnet URI
  AND clears the indexer pin so routing picks qBit by capability.
- error envelope on auth / 404 / 5xx / network failures.
- ``filter_candidates_for_magnet`` drops every grabarr_direct row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.downloaders.models import DownloadClient
from romarr.downloaders.routing import RoutingCandidate
from romarr.metadata.encryption import encrypt
from romarr.search.dispatch_grabarr import (
    GrabarrPreResolveError,
    fetch_resolve,
    filter_candidates_for_magnet,
    maybe_pre_resolve,
)
from romarr.search.types import Candidate


# ---- helpers -------------------------------------------------------------


def _candidate(url: str) -> Candidate:
    return Candidate(
        indexer_id=1,
        indexer_guid="guid-abc",
        title="Sample",
        download_url=url,
    )


def _indexer(
    *,
    impl: str = "grabarr",
    api_key: bytes | None = encrypt(b"rmk_test"),
    pin: int | None = 7,
) -> Any:
    return SimpleNamespace(
        id=1,
        implementation=impl,
        api_key_encrypted=api_key,
        download_client_id=pin,
    )


# ---- URL parsing + passthrough ------------------------------------------


@pytest.mark.asyncio
async def test_passthrough_for_newznab_indexer(
    async_session: AsyncSession,
) -> None:
    cand = _candidate("https://idx.test/some.nzb")
    out_cand, out_pin, snap = await maybe_pre_resolve(
        candidate=cand,
        indexer_row=_indexer(impl="newznab", pin=42),
        db=async_session,
    )
    assert out_cand is cand
    assert out_pin == 42
    assert snap is None


@pytest.mark.asyncio
async def test_passthrough_for_torznab_indexer(
    async_session: AsyncSession,
) -> None:
    cand = _candidate("https://idx.test/some.torrent")
    out_cand, out_pin, snap = await maybe_pre_resolve(
        candidate=cand,
        indexer_row=_indexer(impl="torznab", pin=11),
        db=async_session,
    )
    assert out_cand is cand
    assert out_pin == 11
    assert snap is None


@pytest.mark.asyncio
async def test_passthrough_for_no_indexer_row(
    async_session: AsyncSession,
) -> None:
    cand = _candidate("https://idx.test/x")
    out_cand, out_pin, snap = await maybe_pre_resolve(
        candidate=cand,
        indexer_row=None,
        db=async_session,
    )
    assert out_cand is cand
    assert out_pin is None
    assert snap is None


@pytest.mark.asyncio
async def test_grabarr_indexer_without_apikey_raises(
    async_session: AsyncSession,
) -> None:
    cand = _candidate("https://g.test/torznab/x/download/tok.torrent")
    with pytest.raises(GrabarrPreResolveError, match="no apikey"):
        await maybe_pre_resolve(
            candidate=cand,
            indexer_row=_indexer(api_key=None),
            db=async_session,
        )


# ---- http_direct -------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_http_direct_keeps_candidate_and_pin(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokHTTP.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokHTTP").mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "http_direct",
                "url": "https://ia.test/file.zip",
                "filename": "file.zip",
                "expected_size": 100,
                "headers": {},
                "checksums": {},
                "expires_at": "2026-05-13T00:00:00Z",
                "source": "internet_archive",
            },
        )
    )
    cand = _candidate(url)
    out_cand, out_pin, snap = await maybe_pre_resolve(
        candidate=cand,
        indexer_row=_indexer(pin=7),
        db=async_session,
    )
    assert out_cand.download_url == url  # unchanged — grabarr_direct re-resolves
    assert out_pin == 7  # linked grabarr_direct pin survives
    assert snap is not None
    assert snap.method == "http_direct"
    assert snap.raw["source"] == "internet_archive"


# ---- torrent_magnet ----------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_torrent_magnet_rewrites_url_and_clears_pin(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokMagnet.torrent"
    magnet = "magnet:?xt=urn:btih:abc123def456&dn=Mario"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokMagnet").mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "torrent_magnet",
                "magnet_uri": magnet,
                "filename": "Mario.z64",
                "filename_hint": "Mario.z64",
                "expected_size": 8388608,
                "headers": {},
                "checksums": {},
                "expires_at": "2026-05-13T00:00:00Z",
                "source": "vimm",
            },
        )
    )
    cand = _candidate(url)
    out_cand, out_pin, snap = await maybe_pre_resolve(
        candidate=cand,
        indexer_row=_indexer(pin=7),
        db=async_session,
    )
    assert out_cand.download_url == magnet
    assert out_pin is None  # routing must NOT pin grabarr_direct for a magnet
    assert snap is not None
    assert snap.method == "torrent_magnet"


@respx.mock
@pytest.mark.asyncio
async def test_torrent_magnet_without_uri_raises(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokBadMagnet.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokBadMagnet").mock(
        return_value=httpx.Response(
            200,
            json={
                "method": "torrent_magnet",
                "magnet_uri": "",
                "expected_size": 100,
                "headers": {},
                "checksums": {},
                "source": "vimm",
                "expires_at": "2026-05-13T00:00:00Z",
            },
        )
    )
    with pytest.raises(GrabarrPreResolveError, match="usable magnet_uri"):
        await maybe_pre_resolve(
            candidate=_candidate(url),
            indexer_row=_indexer(),
            db=async_session,
        )


@respx.mock
@pytest.mark.asyncio
async def test_unsupported_method_raises(async_session: AsyncSession) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokWeird.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokWeird").mock(
        return_value=httpx.Response(200, json={"method": "warp_drive"})
    )
    with pytest.raises(GrabarrPreResolveError, match="protocol_version"):
        await maybe_pre_resolve(
            candidate=_candidate(url),
            indexer_row=_indexer(),
            db=async_session,
        )


# ---- error paths -------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_401_surfaces_pre_resolve_error(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokAuth.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokAuth").mock(
        return_value=httpx.Response(401, json={"code": "unauthenticated"})
    )
    with pytest.raises(GrabarrPreResolveError, match="rejected the apikey"):
        await maybe_pre_resolve(
            candidate=_candidate(url),
            indexer_row=_indexer(),
            db=async_session,
        )


@respx.mock
@pytest.mark.asyncio
async def test_404_token_expired_surfaces_pre_resolve_error(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokGone.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokGone").mock(
        return_value=httpx.Response(404, json={"code": "guid_not_found"})
    )
    with pytest.raises(GrabarrPreResolveError, match="expired"):
        await maybe_pre_resolve(
            candidate=_candidate(url),
            indexer_row=_indexer(),
            db=async_session,
        )


@respx.mock
@pytest.mark.asyncio
async def test_network_error_surfaces_pre_resolve_error(
    async_session: AsyncSession,
) -> None:
    base = "https://grabarr.lan"
    url = f"{base}/torznab/roms/download/tokNet.torrent"
    respx.get(f"{base}/romarr/roms/api/v1/resolve/tokNet").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(GrabarrPreResolveError, match="network failure"):
        await maybe_pre_resolve(
            candidate=_candidate(url),
            indexer_row=_indexer(),
            db=async_session,
        )


@pytest.mark.asyncio
async def test_malformed_url_surfaces_pre_resolve_error(
    async_session: AsyncSession,
) -> None:
    # Looks like a download URL but isn't on the Torznab path.
    with pytest.raises(GrabarrPreResolveError, match="expected shape"):
        await fetch_resolve(
            url="https://example.test/just/a/random/path",
            apikey="key",
        )


# ---- filter_candidates_for_magnet ---------------------------------------


@pytest.mark.asyncio
async def test_filter_drops_grabarr_direct_rows(
    async_session: AsyncSession,
) -> None:
    # Seed: one qBit + one grabarr_direct row.
    async_session.add_all(
        [
            DownloadClient(
                name="qbit",
                type="qbittorrent",
                host="qbit.lan",
                port=8080,
                priority=1,
                enable_for_torrents=True,
            ),
            DownloadClient(
                name="grabarr",
                type="grabarr_direct",
                host="grabarr.lan",
                port=8081,
                priority=10,
                enable_for_torrents=True,
            ),
        ]
    )
    await async_session.commit()

    # Build routing candidates that mirror the rows we just seeded.
    rows = (
        await async_session.execute(
            DownloadClient.__table__.select()
        )
    ).all()
    candidates = [
        RoutingCandidate(
            id=r.id,
            priority=r.priority,
            enabled=r.enabled,
            enable_for_torrents=r.enable_for_torrents,
            enable_for_usenet=r.enable_for_usenet,
        )
        for r in rows
    ]
    assert len(candidates) == 2

    filtered = await filter_candidates_for_magnet(
        candidates=candidates, db=async_session
    )
    # Only the qBit row remains.
    assert len(filtered) == 1
    qbit_id = next(r.id for r in rows if r.type == "qbittorrent")
    assert filtered[0].id == qbit_id


@pytest.mark.asyncio
async def test_filter_is_identity_when_no_grabarr_direct(
    async_session: AsyncSession,
) -> None:
    cands = [
        RoutingCandidate(
            id=5, priority=1, enabled=True,
            enable_for_torrents=True, enable_for_usenet=False,
        )
    ]
    out = await filter_candidates_for_magnet(
        candidates=cands, db=async_session
    )
    assert out == cands
