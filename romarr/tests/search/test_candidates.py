"""Winner selector tests (T025-T026 / FR-017)."""

from __future__ import annotations

from romarr.search.candidates import select_winners
from romarr.search.state import IndexerMeta
from romarr.search.types import (
    Candidate,
    Rejection,
    RejectionCode,
    ScoreBreakdown,
    ScoreContribution,
)


def _accepted(
    *,
    indexer_id: int,
    indexer_guid: str,
    matched_release_id: int | None,
    score: int,
) -> Candidate:
    breakdown = ScoreBreakdown(
        total=score,
        contributions=[
            ScoreContribution(source="region", name="USA", value=score)
        ],
    )
    return Candidate(
        indexer_id=indexer_id,
        indexer_guid=indexer_guid,
        title=f"Result {indexer_guid}",
        download_url=f"https://idx.test/{indexer_guid}",
        matched_release_id=matched_release_id,
        matched_game_id=1,
        score_breakdown=breakdown,
        rejection=None,
        would_auto_reject=False,
    )


def _rejected(*, indexer_id: int, indexer_guid: str, matched_release_id: int) -> Candidate:
    return Candidate(
        indexer_id=indexer_id,
        indexer_guid=indexer_guid,
        title=f"Bad {indexer_guid}",
        download_url=f"https://idx.test/{indexer_guid}",
        matched_release_id=matched_release_id,
        matched_game_id=1,
        score_breakdown=None,
        rejection=Rejection(code=RejectionCode.NO_GAME_MATCH, message="bad"),
        would_auto_reject=True,
    )


# ---------------------------------------------------------------------------
# T025 — winner per Release slot
# ---------------------------------------------------------------------------


def test_highest_score_wins_per_slot() -> None:
    candidates = [
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=10, score=50),
        _accepted(indexer_id=2, indexer_guid="g2", matched_release_id=10, score=80),
        _accepted(indexer_id=1, indexer_guid="g3", matched_release_id=10, score=60),
    ]
    winners = select_winners(candidates)
    assert set(winners) == {10}
    assert winners[10].indexer_guid == "g2"
    assert winners[10].score_breakdown is not None
    assert winners[10].score_breakdown.total == 80


def test_separate_release_slots_get_separate_winners() -> None:
    candidates = [
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=10, score=50),
        _accepted(indexer_id=2, indexer_guid="g2", matched_release_id=20, score=10),
    ]
    winners = select_winners(candidates)
    assert set(winners) == {10, 20}


def test_rejected_candidates_excluded() -> None:
    candidates = [
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=10, score=50),
        _rejected(indexer_id=2, indexer_guid="bad", matched_release_id=10),
    ]
    winners = select_winners(candidates)
    assert winners[10].indexer_guid == "g1"


def test_candidates_without_release_id_skipped() -> None:
    candidates = [
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=None, score=50),
    ]
    assert select_winners(candidates) == {}


# ---------------------------------------------------------------------------
# T026 — deterministic tie-breaker
# ---------------------------------------------------------------------------


def test_tie_broken_by_indexer_priority() -> None:
    candidates = [
        _accepted(indexer_id=2, indexer_guid="g2", matched_release_id=10, score=80),
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=10, score=80),
    ]
    indexer_meta = (
        IndexerMeta(id=1, priority=99),  # high priority value = LESS preferred
        IndexerMeta(id=2, priority=1),   # priority=1 wins
    )
    winners = select_winners(candidates, indexer_meta=indexer_meta)
    assert winners[10].indexer_id == 2


def test_tie_broken_by_indexer_id_when_priorities_equal() -> None:
    """Priority 5 vs priority 5 → lower id wins."""
    candidates = [
        _accepted(indexer_id=7, indexer_guid="g7", matched_release_id=10, score=80),
        _accepted(indexer_id=3, indexer_guid="g3", matched_release_id=10, score=80),
    ]
    indexer_meta = (
        IndexerMeta(id=3, priority=5),
        IndexerMeta(id=7, priority=5),
    )
    winners = select_winners(candidates, indexer_meta=indexer_meta)
    assert winners[10].indexer_id == 3


def test_tie_broken_by_guid_when_priority_and_id_equal() -> None:
    """Same indexer (so same priority + id), different guids → lex GUID wins."""
    candidates = [
        _accepted(indexer_id=1, indexer_guid="zebra", matched_release_id=10, score=80),
        _accepted(indexer_id=1, indexer_guid="alpha", matched_release_id=10, score=80),
    ]
    winners = select_winners(candidates)
    assert winners[10].indexer_guid == "alpha"


def test_winner_selection_is_stable_across_input_order() -> None:
    """Same candidates, different list order → same winner every time."""
    base = [
        _accepted(indexer_id=1, indexer_guid="g1", matched_release_id=10, score=80),
        _accepted(indexer_id=2, indexer_guid="g2", matched_release_id=10, score=80),
    ]
    indexer_meta = (
        IndexerMeta(id=1, priority=10),
        IndexerMeta(id=2, priority=5),
    )
    forward = select_winners(base, indexer_meta=indexer_meta)
    reverse = select_winners(list(reversed(base)), indexer_meta=indexer_meta)
    assert forward == reverse
    assert forward[10].indexer_id == 2  # priority=5 wins
