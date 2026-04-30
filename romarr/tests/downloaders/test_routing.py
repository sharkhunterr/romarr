"""Routing tests (T045-T050)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from romarr.downloaders.errors import NoEligibleClientError
from romarr.downloaders.routing import (
    RoutingCandidate,
    consume_decision,
    route_release,
    select_nzb_form,
    select_torrent_form,
)
from romarr.downloaders.types import (
    NzbBytes,
    NzbUrl,
    SourceKind,
    TorrentBytes,
    TorrentMagnet,
    TorrentUrl,
)


def _qbit(id_: int, *, priority: int = 1, enabled: bool = True) -> RoutingCandidate:
    return RoutingCandidate(
        id=id_,
        priority=priority,
        enabled=enabled,
        enable_for_torrents=True,
        enable_for_usenet=False,
    )


def _sab(id_: int, *, priority: int = 1, enabled: bool = True) -> RoutingCandidate:
    return RoutingCandidate(
        id=id_,
        priority=priority,
        enabled=enabled,
        enable_for_torrents=False,
        enable_for_usenet=True,
    )


# ---------------------------------------------------------------------------
# T045 — torrent → torrent client
# ---------------------------------------------------------------------------


def test_torrent_to_torrent_client() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[_qbit(1), _sab(2)],
    )
    assert decision.chosen_client_id == 1
    assert decision.chosen_via == "priority"
    assert decision.source_kind == SourceKind.TORRENT
    assert decision.candidates_considered == [1, 2]
    assert decision.rejection_reason is None


# ---------------------------------------------------------------------------
# T046 — nzb → usenet client
# ---------------------------------------------------------------------------


def test_nzb_to_usenet_client() -> None:
    decision = route_release(
        source_kind=SourceKind.USENET,
        indexer_download_client_id=None,
        candidates=[_qbit(1), _sab(2)],
    )
    assert decision.chosen_client_id == 2
    assert decision.chosen_via == "priority"
    assert decision.source_kind == SourceKind.USENET


# ---------------------------------------------------------------------------
# T047 — indexer override wins (FR-014)
# ---------------------------------------------------------------------------


def test_indexer_override_wins() -> None:
    high_priority = _qbit(1, priority=1)
    pinned = _qbit(2, priority=99)  # would lose on priority alone
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=2,
        candidates=[high_priority, pinned],
    )
    assert decision.chosen_client_id == 2
    assert decision.chosen_via == "indexer_override"


# ---------------------------------------------------------------------------
# T048 — pinned but unsuitable falls back to priority + warns (FR-014 mismatch)
# ---------------------------------------------------------------------------


def test_indexer_override_unsuitable_falls_back() -> None:
    """Indexer pins a SAB (Usenet-only) for a torrent release.
    Routing falls back to priority and records the rejection reason."""
    qbit = _qbit(1, priority=10)
    sab = _sab(2)  # pinned but cannot take a torrent
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=2,
        candidates=[qbit, sab],
    )
    assert decision.chosen_client_id == 1
    assert decision.chosen_via == "priority"
    assert decision.rejection_reason is not None
    assert "indexer-pinned" in decision.rejection_reason
    assert "2" in decision.rejection_reason


def test_indexer_override_disabled_falls_back() -> None:
    """Indexer pins a disabled client; routing falls back."""
    qbit = _qbit(1)
    pinned = _qbit(2, enabled=False)
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=2,
        candidates=[qbit, pinned],
    )
    assert decision.chosen_client_id == 1
    assert decision.chosen_via == "priority"
    assert decision.rejection_reason is not None
    assert "disabled" in decision.rejection_reason


def test_indexer_override_unknown_id_falls_back() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=999,
        candidates=[_qbit(1)],
    )
    assert decision.chosen_client_id == 1
    assert decision.chosen_via == "priority"
    assert decision.rejection_reason is not None
    assert "not found" in decision.rejection_reason


# ---------------------------------------------------------------------------
# T049 — no eligible client
# ---------------------------------------------------------------------------


def test_no_eligible_client_torrent() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[_sab(1)],  # only a Usenet client
    )
    assert decision.chosen_client_id is None
    assert decision.chosen_via == "no_eligible_client"
    assert decision.rejection_reason is not None


def test_no_eligible_client_no_clients_at_all() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[],
    )
    assert decision.chosen_via == "no_eligible_client"


def test_no_eligible_client_all_disabled() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[_qbit(1, enabled=False)],
    )
    assert decision.chosen_via == "no_eligible_client"


def test_consume_decision_raises_when_no_eligible() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[_sab(1)],
    )
    with pytest.raises(NoEligibleClientError):
        consume_decision(decision)


def test_consume_decision_returns_id_when_chosen() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[_qbit(1)],
    )
    assert consume_decision(decision) == 1


# ---------------------------------------------------------------------------
# Priority tie-breaker (lower wins; ties broken by id)
# ---------------------------------------------------------------------------


def test_priority_lower_wins() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[
            _qbit(1, priority=50),
            _qbit(2, priority=10),
            _qbit(3, priority=25),
        ],
    )
    assert decision.chosen_client_id == 2  # priority=10 wins


def test_priority_tie_broken_by_id() -> None:
    decision = route_release(
        source_kind=SourceKind.TORRENT,
        indexer_download_client_id=None,
        candidates=[
            _qbit(7, priority=5),
            _qbit(3, priority=5),
            _qbit(5, priority=5),
        ],
    )
    assert decision.chosen_client_id == 3  # lowest id at same priority


# ---------------------------------------------------------------------------
# T050 — JSONL corpus (30 mixed releases)
# ---------------------------------------------------------------------------


_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures/routing/corpus.jsonl"
)


def _load_corpus() -> list[dict[str, object]]:
    with _FIXTURE.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _corpus_id(row: dict[str, object]) -> str:
    label = row.get("_label")
    return str(label) if label else "row"


_CORPUS = _load_corpus()


@pytest.mark.parametrize("row", _CORPUS, ids=[_corpus_id(r) for r in _CORPUS])
def test_corpus_30_releases(row: dict[str, object]) -> None:
    candidates_payload = row["candidates"]
    assert isinstance(candidates_payload, list)
    candidates = [RoutingCandidate(**c) for c in candidates_payload]
    decision = route_release(
        source_kind=SourceKind(row["source_kind"]),
        indexer_download_client_id=row["indexer_download_client_id"],  # type: ignore[arg-type]
        candidates=candidates,
    )
    assert decision.chosen_client_id == row["expected_chosen_client_id"], row
    assert decision.chosen_via == row["expected_chosen_via"], row


def test_corpus_has_30_rows() -> None:
    assert len(_CORPUS) == 30


# ---------------------------------------------------------------------------
# Source-form preference selectors (CL002 / FR-003a)
# ---------------------------------------------------------------------------


def test_select_torrent_form_url_over_bytes_over_magnet() -> None:
    forms = [
        TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:abc"),
        TorrentBytes(data=b"raw"),
        TorrentUrl(url="https://x.test/file.torrent"),  # type: ignore[arg-type]
    ]
    chosen = select_torrent_form(forms)
    assert isinstance(chosen, TorrentUrl)


def test_select_torrent_form_bytes_over_magnet() -> None:
    forms = [
        TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:abc"),
        TorrentBytes(data=b"raw"),
    ]
    assert isinstance(select_torrent_form(forms), TorrentBytes)


def test_select_torrent_form_magnet_only() -> None:
    forms = [TorrentMagnet(magnet_uri="magnet:?xt=urn:btih:abc")]
    assert isinstance(select_torrent_form(forms), TorrentMagnet)


def test_select_torrent_form_empty() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_torrent_form([])


def test_select_nzb_form_url_over_bytes() -> None:
    forms = [
        NzbBytes(data=b"raw"),
        NzbUrl(url="https://x.test/file.nzb"),  # type: ignore[arg-type]
    ]
    assert isinstance(select_nzb_form(forms), NzbUrl)


def test_select_nzb_form_bytes_only() -> None:
    forms = [NzbBytes(data=b"raw")]
    assert isinstance(select_nzb_form(forms), NzbBytes)


def test_select_nzb_form_empty() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_nzb_form([])
