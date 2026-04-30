"""Routing value type tests."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import TypeAdapter

from romarr.downloaders.types import (
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


def test_torrent_source_discriminated_union() -> None:
    adapter: TypeAdapter[TorrentSource] = TypeAdapter(TorrentSource)
    parsed_url = adapter.validate_python(
        {"kind": "torrent_url", "url": "https://example.test/file.torrent"}
    )
    assert isinstance(parsed_url, TorrentUrl)

    parsed_magnet = adapter.validate_python(
        {"kind": "torrent_magnet", "magnet_uri": "magnet:?xt=urn:btih:abc"}
    )
    assert isinstance(parsed_magnet, TorrentMagnet)

    parsed_bytes = adapter.validate_python(
        {"kind": "torrent_bytes", "data": b"\x01\x02"}
    )
    assert isinstance(parsed_bytes, TorrentBytes)


def test_nzb_source_discriminated_union() -> None:
    adapter: TypeAdapter[NzbSource] = TypeAdapter(NzbSource)
    assert isinstance(
        adapter.validate_python(
            {"kind": "nzb_url", "url": "https://example.test/file.nzb"}
        ),
        NzbUrl,
    )
    assert isinstance(
        adapter.validate_python({"kind": "nzb_bytes", "data": b"\x01"}),
        NzbBytes,
    )


def test_download_status_progress_bounds() -> None:
    snapshot = DownloadStatus(
        client_id=1,
        client_native_id="nzo-1",
        name="Sonic",
        state=DownloadState.DOWNLOADING,
        progress=0.5,
        eta_seconds=120,
        download_rate_bps=10_000_000,
        fetched_at=datetime.now(UTC),
    )
    assert snapshot.progress == 0.5
    assert snapshot.completed_paths == []


def test_connectivity_test_result_ok() -> None:
    result = ConnectivityTestResult(
        ok=True,
        client_version="qBittorrent v4.6.5",
        warnings=[
            ConnectivityWarning(
                code="category_missing",
                message="No 'romarr' category",
            )
        ],
    )
    assert result.ok is True
    assert result.error_code is None
    assert result.warnings[0].code == "category_missing"


def test_connectivity_test_result_failure() -> None:
    result = ConnectivityTestResult(
        ok=False,
        error_code="auth",
        error_message="bad credentials",
    )
    assert result.ok is False
    assert result.error_code == "auth"


def test_routing_decision_no_eligible() -> None:
    decision = RoutingDecision(
        chosen_client_id=None,
        chosen_via="no_eligible_client",
        source_kind=SourceKind.TORRENT,
        candidates_considered=[1, 2],
        rejection_reason="no torrent-capable client enabled",
    )
    assert decision.chosen_client_id is None
    assert decision.chosen_via == "no_eligible_client"
