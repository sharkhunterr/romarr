"""RSS sync round orchestrator (T053 / FR-027 / US7).

Polls every enabled indexer's RSS feed (no query — just the
indexer's recent activity), runs each result through the pure
pipeline, and writes one search-history row per indexer.

Key invariants:

  * **RSS bypasses the cache** (FR-027): the cache helper is invoked
    with ``bypass=True`` so a stale row can never poison RSS
    decisions. Verified by :mod:`tests.search.test_cache`.
  * **rss_auto_grab gate** (US7 / FR-027): when an indexer's
    ``rss_auto_grab=False``, results are recorded in
    ``search_history`` but never passed downstream as grabs — the
    operator opted out at the indexer level.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from romarr.indexers.errors import IndexerAuthError, IndexerProtocolError
from romarr.search.history import record_round
from romarr.search.pipeline import run_pipeline
from romarr.search.preload import (
    preload_custom_formats,
    preload_default_profiles,
    preload_indexers,
    preload_library_state,
)
from romarr.search.types import Candidate, SearchRoundReport

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.indexers.client import NewznabClient


def _none_dat(_a: str | None, _b: str | None) -> Literal["verified", "hack", "none"]:
    return "none"


_ClientFactory = Callable[[int], Awaitable["NewznabClient"]]


async def run_rss_sync(
    *,
    session: AsyncSession,
    client_factory: _ClientFactory,
    indexer_ids: list[int] | None = None,
    correlation_id: str | None = None,
) -> SearchRoundReport:
    """Run one RSS-sync round across enabled indexers.

    The round writes one ``search_history`` row per indexer. RSS
    results from indexers with ``rss_auto_grab=False`` are recorded
    but excluded from ``report.grabs`` so the dispatcher never
    auto-grabs them (US7).
    """
    correlation = correlation_id or str(uuid4())
    started_at = datetime.now(UTC)

    indexer_rows = await preload_indexers(
        session, indexer_ids=indexer_ids, require_rss=True
    )
    library_state = await preload_library_state(session)
    profiles = await preload_default_profiles(session)
    custom_formats = await preload_custom_formats(session)

    quality = profiles.get("quality")
    region = profiles.get("region")
    dump = profiles.get("dump")
    language = profiles.get("language")

    candidates: list[Candidate] = []
    grabs: list[Candidate] = []
    indexer_outcomes: dict[int, str] = {}
    history_entries: list[dict[str, object]] = []

    if quality is None or region is None or dump is None or language is None:
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        return SearchRoundReport(
            correlation_id=UUID(correlation),
            search_type="rss",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            candidates=[],
            grabs=[],
            indexer_outcomes={},
            overcap_indexers=[],
        )

    async def _poll_one(
        indexer_id: int, *, auto_grab: bool
    ) -> tuple[int, list[Candidate], list[Candidate], str]:
        try:
            client = await client_factory(indexer_id)
        except Exception:
            return indexer_id, [], [], "failed"
        try:
            try:
                results = await client.rss(categories=None)
            except (IndexerAuthError, IndexerProtocolError):
                return indexer_id, [], [], "failed"
            except Exception:
                return indexer_id, [], [], "failed"
        finally:
            await client.aclose()

        all_candidates: list[Candidate] = []
        eligible_grabs: list[Candidate] = []
        for result in results:
            candidate = run_pipeline(
                result=result,
                library_state=library_state,
                dat_lookup=_none_dat,
                quality_profile=quality,
                region_profile=region,
                dump_profile=dump,
                language_profile=language,
                custom_formats=custom_formats,
                file_format="",
            )
            all_candidates.append(candidate)
            # US7 / FR-027: only forward as grabs when the indexer
            # has rss_auto_grab=true AND the candidate cleared the
            # pipeline. Score ≤ 0 isn't grabbed automatically.
            if (
                auto_grab
                and candidate.rejection is None
                and candidate.score_breakdown is not None
                and candidate.score_breakdown.total > 0
            ):
                eligible_grabs.append(candidate)
        return indexer_id, all_candidates, eligible_grabs, "ok"

    fan_out = [_poll_one(row.id, auto_grab=row.rss_auto_grab) for row in indexer_rows]
    if fan_out:
        for indexer_id, per_indexer, eligible, outcome in await asyncio.gather(
            *fan_out, return_exceptions=False
        ):
            indexer_outcomes[indexer_id] = outcome
            candidates.extend(per_indexer)
            grabs.extend(eligible)
            history_entries.append(
                {
                    "indexer_id": indexer_id,
                    "results_count": len(per_indexer),
                    "no_grab_reason": (
                        None
                        if outcome == "ok" and eligible
                        else "no_eligible_candidates"
                        if outcome == "ok"
                        else "all_indexers_failed"
                    ),
                }
            )

    if history_entries:
        await record_round(
            session,
            correlation_id=correlation,
            search_type="rss",
            query=None,
            indexer_results=history_entries,
        )

    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    return SearchRoundReport(
        correlation_id=UUID(correlation),
        search_type="rss",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        candidates=candidates,
        grabs=grabs,
        indexer_outcomes=indexer_outcomes,
        overcap_indexers=[],
    )


__all__ = ["run_rss_sync"]
