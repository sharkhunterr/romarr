"""RSS sync round orchestrator (T053 / FR-027 / US7).

Polls every enabled indexer's RSS feed (no query — just the
indexer's recent activity), runs each result through the pure
pipeline, and writes one search-history row per (indexer, game).

Key invariants:

  * **RSS bypasses the cache** (FR-027): the cache helper is invoked
    with ``bypass=True`` so a stale row can never poison RSS
    decisions. Verified by :mod:`tests.search.test_cache`.
  * **rss_auto_grab gate** (US7 / FR-027): when an indexer's
    ``rss_auto_grab=False``, results are recorded in
    ``search_history`` but never passed downstream as grabs — the
    operator opted out at the indexer level.
  * **Same scoring path as manual search** — RSS builds the same
    ``dat_lookup`` (from ``dat_entry``) and ``owned_lookup`` (from
    ``dump``) that the manual round uses, enforces the same
    title-vs-game ``platform_mismatch`` reject, and grabs ONE
    candidate per matched game (the highest score). Two different
    flows that pick different files for the same wanted release
    would be the worst kind of surprise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select

from romarr.domain.models import Platform
from romarr.indexers.errors import IndexerAuthError, IndexerProtocolError
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
    build_db_dat_lookup,
    build_owned_lookup,
    load_min_scores_by_game,
    none_dat,
    none_owned,
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


_ClientFactory = Callable[[int], Awaitable["NewznabClient"]]


def _build_history_entries(
    *,
    indexer_id: int,
    indexer_candidates: list[Candidate],
    grabbed_candidate_ids: set[int],
    outcome: str,
    failure_detail: str | None,
    auto_grab_enabled: bool,
    min_score: int = 0,
) -> list[dict[str, object]]:
    """Convert one indexer's RSS poll into per-game history rows.

    Why per-game and not per-indexer (the old shape): the operator's
    Activity → History tab is anchored on the *game* — each row reads
    "Game X — search via Y returned N results, top scorer = Z, reason
    not grabbed = …". A single per-indexer row with just a count gave
    no way to answer "did the RSS see my missing GBA game?". Now each
    indexer × game pair gets its own row carrying the best candidate's
    score, breakdown, release id, and a precise non-grab reason —
    everything the existing :class:`HistoryRow` already knows how to
    render.

    Rules:
      * Fetch failure → ONE row with ``game_id=None``,
        ``no_grab_reason="indexer_failed: <detail>"`` so the operator
        sees Prowlarr is down rather than silence.
      * Candidates that the pipeline couldn't bind to a library game
        (``matched_game_id is None``) collapse into a single
        ``unidentified`` row — usually noise from the RSS feed.
      * Each identified game gets one row with the best candidate's
        score / score_breakdown / release id, and a non-grab reason
        chosen for actionability (the pipeline's hard reject beats a
        soft ``score_too_low``; ``auto_grab_disabled`` beats both
        when the operator opted out at the indexer level).
    """
    if outcome != "ok":
        return [
            {
                "indexer_id": indexer_id,
                "results_count": 0,
                "no_grab_reason": f"indexer_failed: {failure_detail}"
                if failure_detail
                else "indexer_failed",
            }
        ]

    if not indexer_candidates:
        return [
            {
                "indexer_id": indexer_id,
                "results_count": 0,
                "no_grab_reason": "empty_feed",
            }
        ]

    by_game: dict[int | None, list[Candidate]] = {}
    for c in indexer_candidates:
        by_game.setdefault(c.matched_game_id, []).append(c)

    entries: list[dict[str, object]] = []
    for game_id, group in by_game.items():
        if game_id is None:
            entries.append(
                {
                    "indexer_id": indexer_id,
                    "game_id": None,
                    "results_count": len(group),
                    "no_grab_reason": "unidentified",
                }
            )
            continue

        # Best candidate for the row's score+breakdown columns. Prefer
        # one that scored (rejection=None and breakdown.total > 0),
        # then by total descending; fall back to anything if every
        # candidate was rejected.
        scored = [
            c
            for c in group
            if c.rejection is None and c.score_breakdown is not None
        ]
        scored.sort(
            key=lambda c: (c.score_breakdown.total if c.score_breakdown else 0),
            reverse=True,
        )
        best = scored[0] if scored else group[0]
        best_total = best.score_breakdown.total if best.score_breakdown else None

        grabbed = any(id(c) in grabbed_candidate_ids for c in group)
        if grabbed:
            no_grab_reason: str | None = None
        elif best.rejection is not None:
            # Hard pipeline reject — surface its code so the operator
            # sees "platform_mismatch" / "dump_rejected" / …
            no_grab_reason = f"rejected: {best.rejection.code.value}"
        elif best_total is not None and best_total <= 0:
            no_grab_reason = "score_too_low"
        elif (
            best_total is not None
            and min_score > 0
            and best_total < min_score
        ):
            # Cleared the pipeline (score > 0) but the operator's
            # profile floor held it back. Carry the actual numbers
            # so the modal can read "best=42 < min=50".
            no_grab_reason = f"below_min_score: {best_total}/{min_score}"
        elif not auto_grab_enabled:
            # All other candidates fit, but the indexer's
            # rss_auto_grab flag held the dispatch back.
            no_grab_reason = "auto_grab_disabled"
        else:
            no_grab_reason = "no_eligible_candidates"

        entries.append(
            {
                "indexer_id": indexer_id,
                "game_id": game_id,
                "release_id": best.matched_release_id,
                "results_count": len(group),
                "score": best_total,
                "score_breakdown": (
                    [c.model_dump() for c in best.score_breakdown.contributions]
                    if best.score_breakdown is not None
                    else None
                ),
                "no_grab_reason": no_grab_reason,
                "grabbed_release_id": (
                    best.matched_release_id if grabbed else None
                ),
                "chosen_indexer_guid": best.indexer_guid if grabbed else None,
            }
        )

    return entries


async def run_rss_sync(
    *,
    session: AsyncSession,
    client_factory: _ClientFactory,
    indexer_ids: list[int] | None = None,
    correlation_id: str | None = None,
) -> SearchRoundReport:
    """Run one RSS-sync round across enabled indexers.

    The round writes one ``search_history`` row per (indexer, game)
    pair. RSS results from indexers with ``rss_auto_grab=False`` are
    recorded but excluded from ``report.grabs`` so the dispatcher
    never auto-grabs them (US7).

    Grab selection is best-score-per-game across all auto-grab
    indexers — even if three indexers each surface five passing
    candidates for the same wanted release, the round dispatches
    exactly one grab (the top score), matching the operator's
    manual-search behaviour.
    """
    correlation = correlation_id or str(uuid4())
    started_at = datetime.now(UTC)

    indexer_rows = await preload_indexers(
        session, indexer_ids=indexer_ids, require_rss=True
    )
    library_state = await preload_library_state(session)
    profiles = await preload_default_profiles(session)
    custom_formats = await preload_custom_formats(session)
    # Pre-cache the full platform catalogue for title-vs-game
    # platform matching. Manual search loads this once per round
    # for the same reason; the table rarely tops a few dozen rows.
    platforms_all = tuple(
        (await session.execute(select(Platform))).scalars().all()
    )
    # Game → platform_id lookup so the per-candidate platform
    # mismatch check stays O(1) (RSS may match dozens of distinct
    # games per tick).
    game_platform: dict[int, int | None] = {
        g.id: g.platform_id for g in library_state.monitored_games
    }

    quality = profiles.get("quality")
    region = profiles.get("region")
    dump = profiles.get("dump")
    language = profiles.get("language")

    candidates: list[Candidate] = []
    grabs: list[Candidate] = []
    indexer_outcomes: dict[int, str] = {}
    history_entries: list[dict[str, object]] = []

    # Default auto-grab floor — the fallback used for candidates
    # whose matched game has no library binding. Per-game floors
    # are looked up from the game's library cascade further down
    # (step 3) so each release honours its own profile.
    min_score = max(0, int(getattr(quality, "auto_grab_min_score", 0) or 0))

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

    async def _fetch_one(
        indexer_id: int,
    ) -> tuple[int, list, str, str | None]:
        """Fetch raw SearchResults from one indexer; defer the
        pipeline so we can pre-build a real ``dat_lookup`` /
        ``owned_lookup`` over the union of hashes across all
        indexers (single SQL roundtrip).
        """
        try:
            client = await client_factory(indexer_id)
        except Exception as exc:
            return indexer_id, [], "failed", f"client_factory: {type(exc).__name__}"
        try:
            try:
                results = await client.rss(categories=None)
            except IndexerAuthError as exc:
                return indexer_id, [], "failed", f"auth_error: {exc}"[:200]
            except IndexerProtocolError as exc:
                return indexer_id, [], "failed", f"protocol_error: {exc}"[:200]
            except Exception as exc:
                return indexer_id, [], "failed", f"{type(exc).__name__}: {exc}"[:200]
        finally:
            await client.aclose()
        return indexer_id, results, "ok", None

    auto_grab_by_indexer: dict[int, bool] = {
        row.id: row.rss_auto_grab for row in indexer_rows
    }

    fetch_outcomes: list[tuple[int, list, str, str | None]] = []
    if indexer_rows:
        fetch_outcomes = list(
            await asyncio.gather(
                *(_fetch_one(row.id) for row in indexer_rows),
                return_exceptions=False,
            )
        )

    # ----------------- Step 1: hash collection + lookups ------------------
    # Build the DAT + owned-hash lookups once per round, scoped to
    # the platforms of the games this round's results could match.
    # That matches what manual.py does on a single platform; for RSS
    # we widen to the set of platforms touched by *any* candidate
    # that already identifies a matched game in the library.
    sha1s: set[str] = set()
    md5s: set[str] = set()
    crc32s: set[str] = set()
    for _idx, raw_results, _out, _det in fetch_outcomes:
        for r in raw_results:
            if r.hash_sha1:
                sha1s.add(r.hash_sha1.lower())
            if getattr(r, "hash_md5", None):
                md5s.add(r.hash_md5.lower())
            if r.hash_crc32:
                crc32s.add(r.hash_crc32.lower())
    candidate_platform_ids = {
        pid for pid in game_platform.values() if pid is not None
    }
    candidate_game_ids = {g.id for g in library_state.monitored_games}
    dat_lookup = (
        await build_db_dat_lookup(
            session,
            platform_id=None,
            hashes_sha1=sha1s,
            hashes_crc32=crc32s,
            platform_ids=candidate_platform_ids,
        )
        if candidate_platform_ids and (sha1s or crc32s)
        else none_dat
    )
    owned_lookup = (
        await build_owned_lookup(
            session, candidate_game_ids, sha1s, md5s, crc32s
        )
        if candidate_game_ids and (sha1s or md5s or crc32s)
        else none_owned
    )

    # ----------------- Step 2: per-indexer pipeline -----------------------
    # Score every result through the SAME pipeline manual search
    # uses (quality / region / dump / language profiles + custom
    # formats + DAT + owned cascades). Apply ``match_platform_in_title``
    # and enforce ``PLATFORM_MISMATCH`` when the title's platform
    # disagrees with the matched game's platform — without this,
    # a "Mario Kart Wii (USA)" RSS hit would auto-grab onto the
    # GBA "Mario Kart" library row just because the fuzzy title
    # match succeeded.
    per_indexer_candidates: dict[int, list[Candidate]] = {}
    for indexer_id, raw_results, outcome, failure_detail in fetch_outcomes:
        indexer_outcomes[indexer_id] = outcome
        if outcome != "ok":
            per_indexer_candidates[indexer_id] = []
            history_entries.extend(
                _build_history_entries(
                    indexer_id=indexer_id,
                    indexer_candidates=[],
                    grabbed_candidate_ids=set(),
                    outcome=outcome,
                    failure_detail=failure_detail,
                    auto_grab_enabled=auto_grab_by_indexer.get(indexer_id, False),
                    min_score=min_score,
                )
            )
            continue

        scored: list[Candidate] = []
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
                # RSS analog of manual.py's slice-458 platform reject:
                # the candidate's matched game (from fuzzy title) is
                # on platform A, but the title spells out platform B.
                # Hard reject so the per-game best-score loop below
                # never grabs a cross-platform release.
                matched_platform = (
                    game_platform.get(candidate.matched_game_id)
                    if candidate.matched_game_id is not None
                    else None
                )
                if (
                    matched_platform is not None
                    and detected.id != matched_platform
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
                                    f"matched game is on platform "
                                    f"#{matched_platform}"
                                ),
                            ),
                            "would_auto_reject": True,
                            "score_breakdown": None,
                        }
                    )
            scored.append(candidate)
        per_indexer_candidates[indexer_id] = scored
        candidates.extend(scored)

    # ----------------- Step 3: best-per-game grab selection ---------------
    # Pool every eligible candidate across auto-grab-enabled
    # indexers, group by matched_game_id, keep the single highest
    # scorer per game. Each game's score floor follows its library
    # binding (operator may run a strict library next to a
    # permissive one); the helper resolves them in one batch.
    candidate_game_ids: set[int] = {
        c.matched_game_id
        for indexer_id, indexer_candidates in per_indexer_candidates.items()
        if auto_grab_by_indexer.get(indexer_id, False)
        for c in indexer_candidates
        if c.matched_game_id is not None
    }
    min_score_by_game = await load_min_scores_by_game(
        session, candidate_game_ids
    )
    eligible_by_game: dict[int, list[Candidate]] = {}
    for indexer_id, indexer_candidates in per_indexer_candidates.items():
        if not auto_grab_by_indexer.get(indexer_id, False):
            continue
        for c in indexer_candidates:
            if c.matched_game_id is None:
                continue
            game_floor = min_score_by_game.get(
                c.matched_game_id, min_score
            )
            if (
                c.rejection is None
                and c.score_breakdown is not None
                and c.score_breakdown.total > 0
                and c.score_breakdown.total >= game_floor
            ):
                eligible_by_game.setdefault(c.matched_game_id, []).append(c)

    grabbed_candidate_ids: set[int] = set()
    for game_id, group in eligible_by_game.items():
        best = max(
            group,
            key=lambda c: (
                c.score_breakdown.total if c.score_breakdown else 0
            ),
        )
        grabs.append(best)
        grabbed_candidate_ids.add(id(best))

    # ----------------- Step 4: per-(indexer, game) history rows -----------
    for indexer_id, indexer_candidates in per_indexer_candidates.items():
        if not indexer_candidates:
            # Already emitted above (fetch-failure branch).
            continue
        history_entries.extend(
            _build_history_entries(
                indexer_id=indexer_id,
                indexer_candidates=indexer_candidates,
                grabbed_candidate_ids=grabbed_candidate_ids,
                outcome="ok",
                failure_detail=None,
                auto_grab_enabled=auto_grab_by_indexer.get(indexer_id, False),
                min_score=min_score,
            )
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
