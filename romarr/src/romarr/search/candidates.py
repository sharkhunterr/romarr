"""Pure-function winner selector (FR-017).

Given a list of pipeline-scored candidates, group by Release slot
and pick the highest-scoring per group. Tie-break deterministically
by ``(indexer.priority asc, indexer.id asc, indexer_guid asc)`` so
the same input always yields the same winner — verifiable via the
1 000-iteration purity test.

Rejected candidates (``rejection`` populated) are dropped from the
selection. The caller still sees them on the round report for the
UI history view; they're just not eligible to win their slot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.search.state import IndexerMeta
    from romarr.search.types import Candidate


def select_winners(
    candidates: list[Candidate],
    *,
    indexer_meta: tuple[IndexerMeta, ...] = (),
) -> dict[int, Candidate]:
    """Return the per-Release-slot winners.

    Key: ``matched_release_id``. Value: the winning :class:`Candidate`.
    Candidates with ``matched_release_id is None`` (no Release
    resolved) are skipped — they can't win a slot.
    """
    priority_for: dict[int, int] = {m.id: m.priority for m in indexer_meta}

    by_slot: dict[int, list[Candidate]] = {}
    for cand in candidates:
        if cand.rejection is not None:
            continue
        if cand.matched_release_id is None:
            continue
        by_slot.setdefault(cand.matched_release_id, []).append(cand)

    winners: dict[int, Candidate] = {}
    for slot, group in by_slot.items():
        group.sort(
            key=lambda c: (
                # Highest score first; bigger total beats smaller.
                -(c.score_breakdown.total if c.score_breakdown else 0),
                # Lower indexer priority wins ties (1 = preferred).
                priority_for.get(c.indexer_id, 100),
                # Lower indexer id wins remaining ties.
                c.indexer_id,
                # Lexicographic GUID — last-resort deterministic tiebreaker.
                c.indexer_guid,
            )
        )
        winners[slot] = group[0]
    return winners


__all__ = ["select_winners"]
