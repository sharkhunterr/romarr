"""Manual search round orchestrator (T041-T042 / FR-005 / US1).

The operator-facing search entry point: take a free-form query +
optional indexer filter, fan out across enabled indexers, run each
result through the pure pipeline, and return a flat report.

Per FR-005 (manual-search default): ``strict=False`` keeps
auto-rejected candidates on the report with
``would_auto_reject=True`` so the operator can see WHY each was
rejected and override via the grab endpoint with ``?force=true``.
``strict=True`` drops them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

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


_RESULT_HARD_CAP = 200
"""FR-029 hard cap per (indexer, query)."""


def _none_dat(_a: str | None, _b: str | None) -> Literal["verified", "hack", "none"]:
    """Default DAT lookup for the manual round.

    Wired to the foundation's DAT cache once spec 008 (importer)
    exposes the hash-to-DAT helper. For MVP every result returns
    ``"none"`` — the pipeline still runs the full gate set, and the
    operator can manually verify via the file-detail UI.
    """
    return "none"


_ClientFactory = Callable[[int], Awaitable["NewznabClient"]]
"""Async factory that yields a :class:`NewznabClient` for one indexer id.

Tests pass a stub factory that returns a respx-mocked client; the
production wiring (slice 5) wires the IndexerRegistry's get(...)
helper.
"""


async def run_manual_search(
    *,
    session: AsyncSession,
    query: str,
    client_factory: _ClientFactory,
    indexer_ids: list[int] | None = None,
    platform_id: int | None = None,
    strict: bool = False,
    correlation_id: str | None = None,
) -> SearchRoundReport:
    """Run one manual search round; return the flat report."""
    correlation = correlation_id or str(uuid4())
    started_at = datetime.now(UTC)

    indexer_rows = await preload_indexers(session, indexer_ids=indexer_ids)
    library_state = await preload_library_state(session)
    profiles = await preload_default_profiles(session)
    custom_formats = await preload_custom_formats(session)

    # FR-006 platform scoping: when the operator searches from a
    # game's detail page, the modal hands us the parent platform_id.
    # The matcher then only considers monitored games on that
    # platform — without this scope, a fuzzy "Mario Kart" hit would
    # bind a result to whatever Mario Kart game scored highest
    # across the entire library, even on the wrong platform.
    if platform_id is not None:
        scoped_games = tuple(
            g
            for g in library_state.monitored_games
            if g.platform_id == platform_id
        )
        scoped_game_ids = {g.id for g in scoped_games}
        scoped_releases = tuple(
            r
            for r in library_state.monitored_releases
            if r.game_id in scoped_game_ids
        )
        library_state = library_state.model_copy(
            update={
                "monitored_games": scoped_games,
                "monitored_releases": scoped_releases,
            }
        )

    quality = profiles.get("quality")
    region = profiles.get("region")
    dump = profiles.get("dump")
    language = profiles.get("language")
    if quality is None or region is None or dump is None or language is None:
        # No profiles seeded yet — the round can't run profile gates.
        finished_at = datetime.now(UTC)
        return SearchRoundReport(
            correlation_id=uuid4().__class__(correlation),
            search_type="manual",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            candidates=[],
            grabs=[],
            indexer_outcomes={},
            overcap_indexers=[],
        )

    candidates: list[Candidate] = []
    indexer_outcomes: dict[int, str] = {}
    overcap_indexers: list[int] = []
    history_entries: list[dict[str, object]] = []

    async def _query_one(indexer_id: int) -> tuple[int, list[Candidate], str, bool]:
        try:
            client = await client_factory(indexer_id)
        except Exception:
            return indexer_id, [], "failed", False
        try:
            try:
                results = await client.search(query, categories=None)
            except (IndexerAuthError, IndexerProtocolError):
                return indexer_id, [], "failed", False
            except Exception:
                return indexer_id, [], "failed", False
        finally:
            await client.aclose()

        # FR-029 hard cap: truncate noisy indexers, flag overcap.
        was_overcap = len(results) > _RESULT_HARD_CAP
        truncated = results[:_RESULT_HARD_CAP]

        per_indexer_candidates: list[Candidate] = []
        for result in truncated:
            candidate = run_pipeline(
                result=result,
                library_state=library_state,
                dat_lookup=_none_dat,
                quality_profile=quality,
                region_profile=region,
                dump_profile=dump,
                language_profile=language,
                custom_formats=custom_formats,
                # Use the filename-parsed format when present so the
                # quality gate can evaluate ``allowed_formats`` and
                # the manual-search row's "Format" facet reflects
                # what the title carries (slice 353).
                file_format=result.file_format or "",
            )
            per_indexer_candidates.append(candidate)
        return indexer_id, per_indexer_candidates, "ok", was_overcap

    fan_out = [
        _query_one(row.id) for row in indexer_rows
    ]
    if fan_out:
        for indexer_id, per_indexer, outcome, was_overcap in await asyncio.gather(
            *fan_out, return_exceptions=False
        ):
            indexer_outcomes[indexer_id] = outcome
            if was_overcap:
                overcap_indexers.append(indexer_id)
            for candidate in per_indexer:
                if strict and candidate.rejection is not None:
                    continue
                candidates.append(candidate)
            history_entries.append(
                {
                    "indexer_id": indexer_id,
                    "results_count": len(per_indexer),
                    "no_grab_reason": (
                        None if outcome == "ok" else "all_indexers_failed"
                    ),
                }
            )

    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    if history_entries:
        await record_round(
            session,
            correlation_id=correlation,
            search_type="manual",
            query=query,
            indexer_results=history_entries,
        )

    from uuid import UUID

    return SearchRoundReport(
        correlation_id=UUID(correlation),
        search_type="manual",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        candidates=candidates,
        grabs=[],  # manual search never auto-dispatches; operator picks
        indexer_outcomes=indexer_outcomes,
        overcap_indexers=overcap_indexers,
    )


__all__ = ["run_manual_search"]
