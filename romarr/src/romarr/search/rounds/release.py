"""Release-search round (T062 / spec 007 FR-005 / US1).

Per-Release manual search variant: instead of a free-form query, the
operator picks an existing :class:`Release` row; the round derives
the query from its parent Game's title and runs every gate against
the Release's bound Library profiles (rather than the factory-default
profiles used by the unscoped manual round).

Path of resolution:
    Release.id → Release.game_id → Game.title (query)
                                 → Game.platform_id (platform filter)
                 Release.library_id → Library → 5 profile FKs (gate set)

When ``library_id`` is None (Release exists but isn't bound to a
Library yet — the Wanted-pre-import case), the round falls back to
the factory-default profiles so the operator can still search.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from sqlalchemy import select

from romarr.domain.models import Game, Release
from romarr.indexers.errors import IndexerAuthError, IndexerProtocolError
from romarr.search.history import record_round
from romarr.search.pipeline import run_pipeline
from romarr.search.preload import (
    preload_custom_formats,
    preload_default_profiles,
    preload_indexers,
    preload_library_profiles,
    preload_library_state,
)
from romarr.search.rounds.manual import _RESULT_HARD_CAP, _ClientFactory
from romarr.search.types import Candidate, SearchRoundReport

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


from romarr.search.state import DatMatchInfo, _NONE_DAT_INFO


def _none_dat(_a: str | None, _b: str | None) -> DatMatchInfo:
    return _NONE_DAT_INFO


async def run_release_search(
    *,
    session: AsyncSession,
    release_id: int,
    client_factory: _ClientFactory,
    indexer_ids: list[int] | None = None,
    strict: bool = False,
    correlation_id: str | None = None,
) -> SearchRoundReport:
    """Run one release-scoped manual search round."""
    correlation = correlation_id or str(uuid4())
    started_at = datetime.now(UTC)

    release = (
        await session.execute(select(Release).where(Release.id == release_id))
    ).scalar_one_or_none()
    if release is None:
        finished_at = datetime.now(UTC)
        return SearchRoundReport(
            correlation_id=UUID(correlation),
            search_type="manual",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            candidates=[],
            grabs=[],
            indexer_outcomes={},
            overcap_indexers=[],
        )

    game = (
        await session.execute(select(Game).where(Game.id == release.game_id))
    ).scalar_one_or_none()
    query = game.title if game is not None else release.name

    if release.library_id is not None:
        profiles = await preload_library_profiles(session, release.library_id)
    else:
        profiles = await preload_default_profiles(session)

    indexer_rows = await preload_indexers(session, indexer_ids=indexer_ids)
    library_state = await preload_library_state(session)
    custom_formats = await preload_custom_formats(session)

    quality = profiles.get("quality")
    region = profiles.get("region")
    dump = profiles.get("dump")
    language = profiles.get("language")
    if quality is None or region is None or dump is None or language is None:
        finished_at = datetime.now(UTC)
        return SearchRoundReport(
            correlation_id=UUID(correlation),
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

    async def _query_one(
        indexer_id: int,
    ) -> tuple[int, list[Candidate], str, bool]:
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
                file_format="",
            )
            per_indexer_candidates.append(candidate)
        return indexer_id, per_indexer_candidates, "ok", was_overcap

    fan_out = [_query_one(row.id) for row in indexer_rows]
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

    from romarr.profiles.scoring import expected_naming_conventions
    return SearchRoundReport(
        correlation_id=UUID(correlation),
        search_type="manual",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        candidates=candidates,
        grabs=[],
        indexer_outcomes=indexer_outcomes,
        overcap_indexers=overcap_indexers,
        profile_expected_conventions=expected_naming_conventions(custom_formats),
    )


__all__ = ["run_release_search"]
