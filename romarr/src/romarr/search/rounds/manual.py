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
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from romarr.domain.models import Platform
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
from romarr.search.rounds._shared import (
    build_db_dat_lookup as _build_db_dat_lookup,
    build_owned_lookup as _build_owned_lookup,
    none_dat as _none_dat,
    none_owned as _none_owned,
)
from romarr.search.types import (
    Candidate,
    Rejection,
    RejectionCode,
    SearchRoundReport,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.indexers.client import NewznabClient


_RESULT_HARD_CAP = 200
"""FR-029 hard cap per (indexer, query)."""


def _manual_history_entries(
    *,
    indexer_id: int,
    indexer_candidates: list[Candidate],
    outcome: str,
    requesting_game_id: int | None = None,
) -> list[dict[str, object]]:
    """Bin one indexer's manual-search candidates into per-game
    ``search_history`` rows.

    Mirrors the RSS round's ``_build_history_entries`` but without
    the auto-grab vocabulary (manual search never dispatches —
    the operator picks). Each identified game gets one row with
    the best candidate's score / breakdown / release id so the
    GameDetail → History tab can show every search that ran for
    that game. Candidates the pipeline couldn't bind to a library
    game collapse into a single ``game_id=None`` row.

    When ``requesting_game_id`` is set (search initiated from a
    specific game card's modal), the round narrows down to ONE
    row for that game — candidates that GAMEMATCH fanned out
    to OTHER monitored games are folded back in as candidates of
    the requesting game. Without this, searching "Mario Hoops
    3-on-3" from game 19's modal would also write rows for games
    17 + 18 because the indexer returned a Minerva meta-torrent
    whose per-file candidates split across every Mario DS game.
    The operator only ever ran ONE search; the history should
    reflect that.
    """
    if outcome != "ok":
        return [
            {
                "indexer_id": indexer_id,
                "results_count": 0,
                "no_grab_reason": "indexer_failed",
                **(
                    {"game_id": requesting_game_id}
                    if requesting_game_id is not None
                    else {}
                ),
            }
        ]
    if not indexer_candidates:
        return [
            {
                "indexer_id": indexer_id,
                "results_count": 0,
                "no_grab_reason": "no_results",
                **(
                    {"game_id": requesting_game_id}
                    if requesting_game_id is not None
                    else {}
                ),
            }
        ]

    # Scoped to a single game's modal: emit ONE row for that game,
    # using the best-scoring candidate across the whole indexer
    # response (the operator's intent was to find releases for this
    # game; whatever GAMEMATCH fanned them out to is internal).
    if requesting_game_id is not None:
        scored_all = [
            c
            for c in indexer_candidates
            if c.rejection is None and c.match_score is not None
        ]
        scored_all.sort(key=lambda c: c.match_score or 0, reverse=True)
        best = scored_all[0] if scored_all else indexer_candidates[0]
        return [
            {
                "indexer_id": indexer_id,
                "game_id": requesting_game_id,
                "release_id": best.matched_release_id,
                "results_count": len(indexer_candidates),
                "score": best.match_score,
                "score_breakdown": (
                    [
                        c.model_dump()
                        for c in best.score_breakdown.contributions
                    ]
                    if best.score_breakdown is not None
                    else None
                ),
                "no_grab_reason": None,
            }
        ]

    by_game: dict[int | None, list[Candidate]] = {}
    for c in indexer_candidates:
        by_game.setdefault(c.matched_game_id, []).append(c)

    has_identified = any(game_id is not None for game_id in by_game)

    entries: list[dict[str, object]] = []
    for game_id, group in by_game.items():
        if game_id is None:
            # The unidentified bucket is torznab noise — every query
            # returns unrelated results. It's only worth recording
            # when *nothing* matched a monitored game (a genuine
            # "found results but none usable" signal); when at least
            # one game matched, this row only surfaces in the History
            # tab as a bogus failed "manual grab", so drop it.
            if has_identified:
                continue
            entries.append(
                {
                    "indexer_id": indexer_id,
                    "game_id": None,
                    "results_count": len(group),
                    "no_grab_reason": "unidentified",
                }
            )
            continue
        scored = [
            c
            for c in group
            if c.rejection is None and c.match_score is not None
        ]
        scored.sort(
            key=lambda c: c.match_score or 0,
            reverse=True,
        )
        best = scored[0] if scored else group[0]
        # Record the canonical ``match_score`` (0-100) — the SAME
        # number the search modal shows and the auto-grab floor
        # gates on — so the History tab can't disagree with either.
        best_score = best.match_score
        entries.append(
            {
                "indexer_id": indexer_id,
                "game_id": game_id,
                "release_id": best.matched_release_id,
                "results_count": len(group),
                "score": best_score,
                "score_breakdown": (
                    [
                        c.model_dump()
                        for c in best.score_breakdown.contributions
                    ]
                    if best.score_breakdown is not None
                    else None
                ),
                # Manual search never auto-grabs; ``no_grab_reason``
                # stays None so the row reads as a clean "search ran"
                # event rather than a failure.
                "no_grab_reason": None,
            }
        )
    return entries


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
    search_type: str = "manual",
    requesting_game_id: int | None = None,
) -> SearchRoundReport:
    """Run one manual search round; return the flat report.

    ``search_type`` defaults to ``"manual"`` (the operator-driven
    call from the UI). Background rounds that re-use this pipeline
    (cutoff, on-add, missing) override it so the persisted
    ``search_history.search_type`` reflects WHO ran the round —
    a critical filter for the Activity feed and the per-game
    history view. Before this knob existed, every cutoff probe
    landed as ``search_type='manual'``, hiding the round behind
    operator-initiated rows and looking like a flood of phantom
    manual searches.
    """
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
            search_type=search_type,
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
    md5s: set[str] = set()
    crc32s: set[str] = set()
    for _indexer_id, raw_results, _outcome, _overcap in fetch_outcomes:
        for r in raw_results:
            if r.hash_sha1:
                sha1s.add(r.hash_sha1.lower())
            if getattr(r, "hash_md5", None):
                md5s.add(r.hash_md5.lower())
            if r.hash_crc32:
                crc32s.add(r.hash_crc32.lower())
    if platform_id is not None and (sha1s or crc32s):
        dat_lookup = await _build_db_dat_lookup(
            session, platform_id, sha1s, crc32s
        )
    else:
        dat_lookup = _none_dat

    # Slice 451 — owned-hash lookup so the search modal can flag
    # candidates whose hash already lives on disk for the matched
    # game. Scoped to the games in the library (the manual round
    # filters by platform_id; library_state.monitored_games is
    # already pre-scoped above).
    candidate_game_ids = {
        g.id for g in library_state.monitored_games
    }
    if candidate_game_ids and (sha1s or md5s or crc32s):
        owned_lookup = await _build_owned_lookup(
            session, candidate_game_ids, sha1s, md5s, crc32s
        )
    else:
        owned_lookup = _none_owned

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
                owned_lookup=owned_lookup,
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
                # Slice 458 — the title spells out a console that
                # differs from the one the operator scoped the
                # search to. Platform mismatch is the single hard
                # reject the soft-scoring model still enforces
                # (slice 456): a GameCube ISO has no business
                # showing up "not rejected" in a GBA search just
                # because the fuzzy title-match bound it to a
                # same-named GBA library row.
                if (
                    platform_id is not None
                    and detected.id != platform_id
                    and candidate.rejection is None
                ):
                    candidate = candidate.model_copy(
                        update={
                            "rejection": Rejection(
                                code=RejectionCode.PLATFORM_MISMATCH,
                                field="platform_id",
                                message=(
                                    f"title advertises platform "
                                    f"#{detected.id} ({detected.slug}); "
                                    f"search is scoped to platform "
                                    f"#{platform_id}"
                                ),
                            ),
                            "would_auto_reject": True,
                            "score_breakdown": None,
                        }
                    )
            per_indexer_candidates.append(candidate)
        for candidate in per_indexer_candidates:
            if strict and candidate.rejection is not None:
                continue
            candidates.append(candidate)
        # Write one search_history row per (indexer, game) so the
        # per-game History tab can surface "a search ran for this
        # game, found N candidates, top score X". The old shape —
        # one aggregate row per indexer with game_id=None — meant
        # the GameDetail history tab only ever showed import rows
        # and never the searches that led to them.
        history_entries.extend(
            _manual_history_entries(
                indexer_id=indexer_id,
                indexer_candidates=per_indexer_candidates,
                outcome=outcome,
                requesting_game_id=requesting_game_id,
            )
        )

    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    if history_entries:
        await record_round(
            session,
            correlation_id=correlation,
            search_type=search_type,
            query=query,
            indexer_results=history_entries,
        )

    from uuid import UUID

    from romarr.profiles.scoring import expected_naming_conventions
    return SearchRoundReport(
        correlation_id=UUID(correlation),
        search_type=search_type,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        candidates=candidates,
        grabs=[],  # manual search never auto-dispatches; operator picks
        indexer_outcomes=indexer_outcomes,
        overcap_indexers=overcap_indexers,
        profile_expected_conventions=expected_naming_conventions(custom_formats),
    )


__all__ = ["run_manual_search"]
