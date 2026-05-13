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

from sqlalchemy import or_, select

from romarr.domain.enums import DumpStatus
from romarr.domain.models import DatEntry, Platform
from romarr.indexers.errors import (
    IndexerAuthError,
    IndexerProtocolError,
    IndexerRateLimitedError,
)
from romarr.search.history import record_round
from romarr.search.pipeline import run_pipeline
from romarr.search.platform_match import match_platform_in_title
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
    """Fallback DAT lookup — used when no platform scope is given
    (so we can't safely query ``dat_entry`` without risking
    cross-platform hash collisions) or when no candidate ships a
    usable hash. Returns ``"none"`` for every call.
    """
    return "none"


def _status_to_outcome(status: str) -> Literal["verified", "hack", "none"]:
    if status == DumpStatus.VERIFIED.value:
        return "verified"
    if status in (
        DumpStatus.HACK.value,
        DumpStatus.BADDUMP.value,
    ):
        return "hack"
    return "none"


async def _build_db_dat_lookup(
    session: AsyncSession,
    platform_id: int,
    hashes_sha1: set[str],
    hashes_crc32: set[str],
) -> Callable[[str | None, str | None], Literal["verified", "hack", "none"]]:
    """Pre-fetch ``dat_entry`` rows whose hashes appear in the
    candidate set for this platform, then expose a sync closure
    that satisfies :class:`DatLookup`.

    Pulling matches up-front lets the pure pipeline stay sync —
    the closure is called inline per result and just dict-looks
    the outcome.
    """
    if not hashes_sha1 and not hashes_crc32:
        return _none_dat

    rows = (
        await session.execute(
            select(
                DatEntry.sha1, DatEntry.crc32, DatEntry.status, DatEntry.source
            )
            .where(
                DatEntry.platform_id == platform_id,
                or_(
                    DatEntry.sha1.in_(hashes_sha1) if hashes_sha1 else False,
                    DatEntry.crc32.in_(hashes_crc32) if hashes_crc32 else False,
                ),
            )
        )
    ).all()
    by_sha1: dict[str, Literal["verified", "hack", "none"]] = {}
    by_crc32: dict[str, Literal["verified", "hack", "none"]] = {}
    # CL001 authority order is enforced by best_match — for the
    # pre-grab cascade a single "is this hash known?" answer is
    # enough, so keep the strongest outcome (verified > hack >
    # none) when the same hash spans multiple sources.
    rank = {"verified": 2, "hack": 1, "none": 0}
    for sha1, crc32, status, _src in rows:
        outcome = _status_to_outcome(status)
        if sha1 and rank[outcome] > rank.get(by_sha1.get(sha1, "none"), 0):
            by_sha1[sha1] = outcome
        if crc32 and rank[outcome] > rank.get(by_crc32.get(crc32, "none"), 0):
            by_crc32[crc32] = outcome

    def _lookup(
        sha1: str | None, crc32: str | None
    ) -> Literal["verified", "hack", "none"]:
        if sha1 and sha1.lower() in by_sha1:
            return by_sha1[sha1.lower()]
        if crc32 and crc32.lower() in by_crc32:
            return by_crc32[crc32.lower()]
        return "none"

    return _lookup


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
    # Pre-cache the full platform catalogue so the per-candidate
    # ``match_platform_in_title`` call below stays fully in memory
    # — we run it on every accepted/rejected row in the round and
    # the catalogue rarely tops a few dozen entries.
    platforms_all = tuple(
        (await session.execute(select(Platform))).scalars().all()
    )

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

    async def _fetch_one(indexer_id: int) -> tuple[int, list, str, bool]:
        """Fetch + truncate raw SearchResults from one indexer.

        The pipeline run is intentionally deferred so we can
        pre-build a real DAT lookup against ``dat_entry`` once
        every indexer has reported in (single SQL roundtrip
        regardless of fan-out width).
        """
        try:
            client = await client_factory(indexer_id)
        except Exception:
            return indexer_id, [], "failed", False
        try:
            try:
                results = await client.search(query, categories=None)
            except IndexerRateLimitedError:
                # Slice 404 — distinct outcome so the UI can tell
                # the operator "indexer told us to slow down" vs
                # the generic "indexer failed".
                return indexer_id, [], "rate_limited", False
            except (IndexerAuthError, IndexerProtocolError):
                return indexer_id, [], "failed", False
            except Exception:
                return indexer_id, [], "failed", False
        finally:
            await client.aclose()

        # FR-029 hard cap: truncate noisy indexers, flag overcap.
        was_overcap = len(results) > _RESULT_HARD_CAP
        truncated = results[:_RESULT_HARD_CAP]
        return indexer_id, truncated, "ok", was_overcap

    fan_out = [_fetch_one(row.id) for row in indexer_rows]
    fetch_outcomes: list[tuple[int, list, str, bool]] = []
    if fan_out:
        fetch_outcomes = list(
            await asyncio.gather(*fan_out, return_exceptions=False)
        )

    # Slice 449 — build a real DAT lookup from ``dat_entry`` for
    # this platform, using the hashes the indexers actually
    # shipped on this round. When no platform scope is set, we
    # fall back to ``_none_dat`` because cross-platform hash
    # collisions would lie about verification.
    sha1s: set[str] = set()
    crc32s: set[str] = set()
    for _indexer_id, raw_results, _outcome, _overcap in fetch_outcomes:
        for r in raw_results:
            if r.hash_sha1:
                sha1s.add(r.hash_sha1.lower())
            if r.hash_crc32:
                crc32s.add(r.hash_crc32.lower())
    if platform_id is not None and (sha1s or crc32s):
        dat_lookup = await _build_db_dat_lookup(
            session, platform_id, sha1s, crc32s
        )
    else:
        dat_lookup = _none_dat

    for indexer_id, raw_results, outcome, was_overcap in fetch_outcomes:
        indexer_outcomes[indexer_id] = outcome
        if was_overcap:
            overcap_indexers.append(indexer_id)
        per_indexer_candidates: list[Candidate] = []
        for result in raw_results:
            candidate = run_pipeline(
                result=result,
                library_state=library_state,
                dat_lookup=dat_lookup,
                quality_profile=quality,
                region_profile=region,
                dump_profile=dump,
                language_profile=language,
                custom_formats=custom_formats,
                file_format=result.file_format or "",
            )
            detected = match_platform_in_title(result.title, platforms_all)
            if detected is not None:
                candidate = candidate.model_copy(
                    update={"platform_id": detected.id}
                )
            per_indexer_candidates.append(candidate)
        for candidate in per_indexer_candidates:
            if strict and candidate.rejection is not None:
                continue
            candidates.append(candidate)
        history_entries.append(
            {
                "indexer_id": indexer_id,
                "results_count": len(per_indexer_candidates),
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
