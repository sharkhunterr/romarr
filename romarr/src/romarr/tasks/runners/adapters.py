"""Per-job runner adapters (T029).

One adapter class per documented default in spec 012's catalogue.
Each wraps the spec-specific entry point that already exists in
the project; where the underlying entry point isn't yet built,
the adapter is a structured stub that records its parameters
and returns ``SUCCESS`` so the scheduler dispatch path can be
exercised end-to-end.

The adapters are constructed by
:func:`romarr.tasks.runner_protocol.build_default_registry` —
they're stateless apart from the optional dependencies they
take at construction time (e.g. ``HealthCheckAdapter`` is given
a :class:`HealthEngine`). The application factory builds them
during lifespan startup, after the real engines exist; tests
substitute their own.

When a downstream adapter's entry point doesn't yet exist the
adapter logs at debug, records the parameters in
``JobResult.summary``, and returns ``SUCCESS``. That's enough
for the scheduler to mark the run as terminal and update the
audit row; the actual work happens once the cross-spec wiring
lands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from romarr.tasks.types import JobResult, JobStatus

if TYPE_CHECKING:
    from romarr.tasks.types import JobContext

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper base — every adapter logs its run + records parameters.


@dataclass
class _AdapterBase:
    """Shared bookkeeping. Subclasses override :meth:`_run` and
    everything else (logging + summary recording) is automatic."""

    job_id: str

    async def run(self, context: JobContext) -> JobResult:
        _logger.info(
            "running job %s (run_id=%s, triggered_by=%s)",
            self.job_id,
            context.job_run_id,
            context.triggered_by.value,
        )
        try:
            result = await self._run(context)
        except Exception as exc:
            _logger.exception(
                "adapter %s raised during run", self.job_id
            )
            return JobResult(
                status=JobStatus.FAILED,
                error_message=f"{exc.__class__.__name__}: {exc}",
            )
        return result

    async def _run(self, context: JobContext) -> JobResult:
        """Override in subclasses. The default ships a
        no-op-success that records the parameters in the
        summary so the scheduler audit captures what was
        triggered."""
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "stub": True,
                "parameters": dict(context.parameters),
            },
        )


# ---------------------------------------------------------------------------
# Adapters that wrap real spec entry points


class HealthCheckAdapter(_AdapterBase):
    """Wraps :class:`romarr.notifications.health.HealthEngine`'s
    ``refresh()`` (spec 011)."""

    def __init__(
        self,
        engine: Any | None = None,
    ) -> None:
        super().__init__(job_id="HealthCheck")
        self._engine = engine

    async def _run(self, context: JobContext) -> JobResult:
        if self._engine is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={
                    "stub": True,
                    "reason": "no health engine wired (deferred to lifespan slice)",
                },
            )
        snapshot = await self._engine.refresh()
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "overall_status": snapshot.overall_status.value,
                "categories": [c.value for c in snapshot.by_category],
            },
        )


# ---------------------------------------------------------------------------
# Adapters that don't yet have a real entry point — stubs that
# pass parameters through and return SUCCESS. The cross-spec
# wiring lands when each upstream module exposes a "run all"
# function suitable for scheduling.


class RssSyncAdapter(_AdapterBase):
    """Wraps spec 007's RSS round + spec 005's dispatch (T060).

    When the JobContext supplies a sessionmaker, the adapter
    calls :func:`run_rss_sync` (full pipeline: feed pull →
    identification → scoring → grabs filter), then dispatches
    every grab via :func:`dispatch_winner` so RSS auto-grabs
    actually land in the configured download client. Without a
    sessionmaker it falls back to the legacy stub.

    Summary keys preserve the slice-204 names
    (``indexers_succeeded`` / ``items_total``) for backward
    compat with operator dashboards; new keys
    (``grabs_dispatched`` / ``grabs_failed``) reflect the
    auto-dispatch wiring."""

    def __init__(self) -> None:
        super().__init__(job_id="RssSync")

    async def _run(self, context: JobContext) -> JobResult:
        from sqlalchemy import select

        from romarr.downloaders.models import DownloadClient
        from romarr.downloaders.routing import RoutingCandidate
        from romarr.indexers.models import Indexer
        from romarr.search._clients import (
            make_download_client_factory,
            make_indexer_client_factory,
        )
        from romarr.search.dispatch import DispatchStatus, dispatch_winner
        from romarr.search.rounds import run_rss_sync
        from romarr.tasks.execution.lifecycle import report_progress

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={"stub": True, "reason": "no sessionmaker"},
            )

        # Pre-count the RSS-enabled indexers so the Activity card
        # surfaces ``processed/total`` from the first tick — same
        # pattern RefreshAllMetadata uses (slice 476).
        async with sessionmaker() as session:
            total_indexers = int(
                (
                    await session.execute(
                        select(Indexer)
                        .where(Indexer.enable_rss.is_(True))
                        .where(Indexer.enabled.is_(True))
                    )
                ).scalars().all().__len__()
            )
        await report_progress(
            sessionmaker,
            job_run_id=context.job_run_id,
            items_processed=0,
            summary_patch={
                "total_items": total_indexers,
                "indexers_succeeded": 0,
                "candidates": 0,
                "grabs_dispatched": 0,
                "grabs_failed": 0,
            },
        )

        async with sessionmaker() as session:
            indexer_factory = make_indexer_client_factory(session)
            download_factory = make_download_client_factory(session)

            # Preload the routing candidate slice once so the
            # per-grab dispatcher doesn't re-query the table.
            client_rows = (
                (await session.execute(select(DownloadClient))).scalars().all()
            )
            routing_candidates = [
                RoutingCandidate(
                    id=r.id,
                    priority=r.priority,
                    enabled=r.enabled,
                    enable_for_torrents=r.enable_for_torrents,
                    enable_for_usenet=r.enable_for_usenet,
                )
                for r in client_rows
            ]

            report = await run_rss_sync(
                session=session, client_factory=indexer_factory
            )

            indexers_succeeded_count = sum(
                1 for v in report.indexer_outcomes.values() if v == "ok"
            )
            # Mid-run snapshot once the pipeline returns but BEFORE
            # we start dispatching — operator sees "pipeline done,
            # now grabbing N candidates" instead of a stale 0/0.
            await report_progress(
                sessionmaker,
                job_run_id=context.job_run_id,
                items_processed=indexers_succeeded_count,
                summary_patch={
                    "total_items": total_indexers,
                    "indexers_succeeded": indexers_succeeded_count,
                    "candidates": len(report.candidates),
                    "grabs_to_dispatch": len(report.grabs),
                    "grabs_dispatched": 0,
                    "grabs_failed": 0,
                },
            )

            # T060: dispatch every grab the RSS round produced.
            # `report.grabs` is already filtered to indexers with
            # `rss_auto_grab=True` and pipeline-clean candidates
            # with score>0 (FR-027), so we can dispatch unconditionally.
            grabs_dispatched = 0
            grabs_failed = 0
            for grab in report.grabs:
                outcome = await dispatch_winner(
                    candidate=grab,
                    candidates=routing_candidates,
                    client_factory=download_factory,
                )
                if outcome.status is DispatchStatus.GRABBED:
                    grabs_dispatched += 1
                else:
                    grabs_failed += 1
                # Per-grab tick so the card moves as dispatches
                # land — cheap, the table is tiny.
                await report_progress(
                    sessionmaker,
                    job_run_id=context.job_run_id,
                    summary_patch={
                        "grabs_dispatched": grabs_dispatched,
                        "grabs_failed": grabs_failed,
                    },
                )

        indexers_succeeded = sum(
            1 for v in report.indexer_outcomes.values() if v == "ok"
        )
        # Final summary written by finish_run via JobResult.summary
        # below — same keys + the legacy ``items_total`` so existing
        # operator dashboards keep working.
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "indexers_total": total_indexers,
                "indexers_succeeded": indexers_succeeded,
                "items_total": len(report.candidates),
                "candidates": len(report.candidates),
                "grabs_dispatched": grabs_dispatched,
                "grabs_failed": grabs_failed,
            },
        )


class CutoffSearchAdapter(_AdapterBase):
    """Wraps spec 007's cutoff search (slice 203 wires the
    real round). When the JobContext supplies a sessionmaker,
    the adapter calls :func:`run_cutoff_search` directly and
    returns the per-Release counts in the summary; without a
    sessionmaker it falls back to the legacy stub."""

    def __init__(self) -> None:
        super().__init__(job_id="CutoffSearch")

    async def _run(self, context: JobContext) -> JobResult:
        from romarr.search.rounds.cutoff import run_cutoff_search

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={"stub": True, "reason": "no sessionmaker"},
            )

        limit = int(context.parameters.get("limit", 50))
        async with sessionmaker() as session:
            result = await run_cutoff_search(session, limit=limit)
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "total": result.total,
                "succeeded": result.succeeded,
                "grabbed": result.grabbed,
            },
        )


class MissingSearchAdapter(_AdapterBase):
    """Wraps spec 007's missing search (slice 203 wires the
    real round). Symmetric shape with ``CutoffSearchAdapter``."""

    def __init__(self) -> None:
        super().__init__(job_id="MissingSearch")

    async def _run(self, context: JobContext) -> JobResult:
        from romarr.search.rounds.missing import run_missing_search

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={"stub": True, "reason": "no sessionmaker"},
            )

        limit = int(context.parameters.get("limit", 50))
        async with sessionmaker() as session:
            result = await run_missing_search(session, limit=limit)
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "total": result.total,
                "succeeded": result.succeeded,
                "grabbed": result.grabbed,
            },
        )


class RefreshGameMetadataAdapter(_AdapterBase):
    """Wraps spec 002's metadata refresh.

    Accepts an optional ``gameId`` parameter for single-game
    refresh; without it, sweeps the full library via
    :func:`refresh_all_metadata` (slice 178 / spec 012 T050).
    The ``platformId`` parameter further scopes the all-games
    path to a single Platform; ``force`` forwards through.

    Single-game path is still a structured stub — wiring it
    into the per-Game refresh requires the JobContext to carry
    a sessionmaker, which lands once spec 012's runner-context
    plumbing exposes one.
    """

    def __init__(self) -> None:
        super().__init__(job_id="RefreshGameMetadata")

    async def _run(self, context: JobContext) -> JobResult:
        game_id = context.parameters.get("gameId")
        if game_id is not None:
            # Single-game refresh — still a stub. Lands when the
            # JobContext exposes a sessionmaker.
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={
                    "stub": True,
                    "scope": "single-game",
                    "gameId": game_id,
                },
            )

        # All-games path — slice 178 wires the real runner.
        import asyncio

        from sqlalchemy import func, select

        from romarr.domain.models import Game
        from romarr.tasks.execution.lifecycle import report_progress
        from romarr.tasks.runners.refresh_all_metadata import (
            refresh_all_metadata,
        )

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            # Older test contexts may not provide one — keep the
            # stub behavior so the scheduler dispatch path stays
            # exercised end-to-end.
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={
                    "stub": True,
                    "scope": "all-games",
                    "gameId": None,
                },
            )

        platform_id = context.parameters.get("platformId")
        force = bool(context.parameters.get("force", False))
        # Pre-count the games we're about to walk so the Activity
        # card surfaces ``processed/total`` from the first tick
        # (slice 476).
        async with sessionmaker() as session:
            total_stmt = select(func.count(Game.id))
            if platform_id is not None:
                total_stmt = total_stmt.where(
                    Game.platform_id == platform_id
                )
            total_games = int(
                (await session.execute(total_stmt)).scalar() or 0
            )
        await report_progress(
            sessionmaker,
            job_run_id=context.job_run_id,
            items_processed=0,
            summary_patch={
                "total_items": total_games,
                "matched": 0,
                "failed": 0,
            },
        )

        def _progress(total: int, refreshed: int, failed: int) -> None:
            # Same fire-and-forget pattern as the LibraryScan
            # adapter — sync callback inside async sweep, drop
            # an asyncio task to write the row.
            task = asyncio.create_task(
                report_progress(
                    sessionmaker,
                    job_run_id=context.job_run_id,
                    items_processed=total,
                    summary_patch={
                        "total_items": total_games,
                        "matched": refreshed,
                        "failed": failed,
                    },
                )
            )
            task.add_done_callback(lambda _: None)

        async with sessionmaker() as session:
            result = await refresh_all_metadata(
                session,
                platform_id=platform_id,
                force=force,
                progress_callback=_progress,
            )
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "scope": "all-games",
                "platformId": platform_id,
                "force": force,
                "total": result.total,
                "refreshed": result.refreshed,
                "failed": result.failed,
            },
        )


class DatUpdateAdapter(_AdapterBase):
    """Wraps the DAT pack auto-refresh (slice 180 / spec 012 T051).

    When a ``sessionmaker`` is available on the JobContext and
    the parameters carry a list of ``sources`` (each of the
    shape ``{"url": ..., "source": ..., "platform_id": ...}``),
    the adapter delegates to :func:`run_dat_update`. Without
    those inputs it falls back to the legacy stub so the
    scheduler dispatch path stays exercised end-to-end.
    """

    def __init__(self) -> None:
        super().__init__(job_id="DatUpdate")

    async def _run(self, context: JobContext) -> JobResult:
        from romarr.tasks.runners.dat_update import (
            DatSourceSpec,
            run_dat_update,
        )

        sessionmaker = getattr(context, "sessionmaker", None)
        raw_sources = context.parameters.get("sources") or []
        if sessionmaker is None or not raw_sources:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={
                    "stub": True,
                    "reason": (
                        "no sessionmaker"
                        if sessionmaker is None
                        else "no sources configured"
                    ),
                },
            )

        specs = [
            DatSourceSpec(
                url=item["url"],
                source=item["source"],
                platform_id=int(item["platform_id"]),
            )
            for item in raw_sources
        ]
        async with sessionmaker() as session:
            result = await run_dat_update(session, sources=specs)

        # Slice 277 — emit OnDatUpdate so live operator sessions
        # see the cache refresh land. We publish one
        # ``OnDatUpdate`` per successfully ingested source (skipping
        # both errored fetches and idempotent re-ingests where
        # nothing actually changed). Best-effort: a missing channel
        # is a silent no-op.
        event_channel = getattr(context, "event_channel", None)
        if event_channel is not None:
            from romarr.notifications.types import OnDatUpdatePayload

            for outcome in result.outcomes:
                if outcome.error is not None or outcome.skipped_idempotent:
                    continue
                try:
                    await event_channel.publish(
                        OnDatUpdatePayload(
                            source=outcome.spec.source,
                            platform=str(outcome.spec.platform_id),
                            entries_count=outcome.inserted,
                            version="",
                        )
                    )
                except Exception:
                    _logger.exception(
                        "DatUpdateAdapter ws emission failed for source=%s",
                        outcome.spec.source,
                    )

        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "total": result.total,
                "succeeded": result.succeeded,
                "failed": result.failed,
            },
        )


class BackupAdapter(_AdapterBase):
    """Wraps the backup runner — snapshots DB + config to
    ``<data>/backups/`` per FR-027a (slice 179 / spec 012 T049).

    When the JobContext exposes a ``sessionmaker`` the adapter
    calls :func:`run_backup` directly; older test contexts
    that don't supply one fall through to the legacy stub
    behavior so the scheduler dispatch path stays exercised.
    """

    def __init__(self) -> None:
        super().__init__(job_id="Backup")

    async def _run(self, context: JobContext) -> JobResult:
        from pathlib import Path

        from romarr.config.settings import get_settings
        from romarr.tasks.runners.backup import run_backup

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={"stub": True},
            )
        settings = get_settings()
        backup_dir = Path(settings.backup_path)
        async with sessionmaker() as session:
            result = await run_backup(
                session,
                backup_dir=backup_dir,
                settings=settings,
            )
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "db_path": str(result.db_path),
                "config_path": str(result.config_path),
                "pruned_count": len(result.pruned),
            },
        )


class LibraryScanAdapter(_AdapterBase):
    """Wraps spec 009's library full-scan (slice 209 wires the
    real scanner). When the JobContext supplies a sessionmaker
    + an optional ``libraryId`` parameter, the adapter:

      1. Loads the targeted Library rows (one if ``libraryId``
         is given, all of them otherwise).
      2. Resolves the accepted-extensions set per Library — the
         platforms_restricted m2m if set, otherwise every
         configured PlatformFormat.
      3. Calls ``full_scan`` per Library.
      4. Aggregates per-Library counts in the JobResult summary.

    Without a sessionmaker, falls back to the legacy stub so
    the scheduler dispatch path stays exercised end-to-end."""

    def __init__(self) -> None:
        super().__init__(job_id="LibraryScan")

    async def _run(self, context: JobContext) -> JobResult:
        import asyncio
        from pathlib import Path

        from sqlalchemy import select

        from romarr.domain.models import PlatformFormat
        from romarr.libraries.models import Library, LibraryPlatform
        from romarr.libraries.scanner.full import full_scan, walk_library
        from romarr.tasks.execution.lifecycle import report_progress

        sessionmaker = getattr(context, "sessionmaker", None)
        if sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={"stub": True, "reason": "no sessionmaker"},
            )

        library_id_param = context.parameters.get("libraryId")
        per_library: list[dict[str, Any]] = []
        scanned = 0
        skipped = 0
        # Slice 475 — running tallies surfaced live on the Activity
        # active-task card via mid-run progress writes.
        total_files_overall = 0
        processed_files_overall = 0
        matched_overall = 0
        unmatched_overall = 0

        async with sessionmaker() as session:
            stmt = select(Library)
            if library_id_param is not None:
                stmt = stmt.where(Library.id == int(library_id_param))
            libraries = (await session.execute(stmt)).scalars().all()

            for library in libraries:
                library_path = Path(library.path)
                if not library_path.exists():
                    skipped += 1
                    per_library.append(
                        {
                            "library_id": library.id,
                            "skipped": True,
                            "reason": "path_missing",
                        }
                    )
                    continue

                # Resolve accepted extensions: per-library
                # allowlist if platforms_restricted, else every
                # known PlatformFormat extension.
                if library.platforms_restricted:
                    allowed_platform_ids = (
                        await session.execute(
                            select(LibraryPlatform.platform_id).where(
                                LibraryPlatform.library_id == library.id
                            )
                        )
                    ).scalars().all()
                    if not allowed_platform_ids:
                        skipped += 1
                        per_library.append(
                            {
                                "library_id": library.id,
                                "skipped": True,
                                "reason": "empty_allowlist",
                            }
                        )
                        continue
                    formats = (
                        await session.execute(
                            select(PlatformFormat.extension).where(
                                PlatformFormat.platform_id.in_(
                                    allowed_platform_ids
                                )
                            )
                        )
                    ).scalars().all()
                else:
                    formats = (
                        await session.execute(
                            select(PlatformFormat.extension)
                        )
                    ).scalars().all()

                accepted = {ext.lstrip(".").lower() for ext in formats}
                if not accepted:
                    skipped += 1
                    per_library.append(
                        {
                            "library_id": library.id,
                            "skipped": True,
                            "reason": "no_known_extensions",
                        }
                    )
                    continue

                # Pre-count the files we're about to walk so the
                # Activity card shows ``processed/total`` right
                # from the first refresh tick.
                library_total = sum(
                    1
                    for _ in walk_library(
                        library_path, accepted_extensions=accepted
                    )
                )
                total_files_overall += library_total
                await report_progress(
                    sessionmaker,
                    job_run_id=context.job_run_id,
                    items_processed=processed_files_overall,
                    summary_patch={
                        "total_items": total_files_overall,
                        "matched": matched_overall,
                        "unmatched": unmatched_overall,
                    },
                )

                # Default-args capture the current loop iteration's
                # values so a re-entrant closure in the next library
                # doesn't trample state — full_scan runs to
                # completion before the loop advances, so the
                # closure only fires for one library's scan, but
                # the defaults are also what keeps ruff B023 quiet.
                def _sink(
                    ev: Any,
                    _base: int = processed_files_overall,
                    _total: int = total_files_overall,
                    _matched: int = matched_overall,
                    _unmatched: int = unmatched_overall,
                ) -> None:
                    # Sync callback inside async full_scan — fire
                    # a background task so the row update never
                    # blocks the scanner loop. ``files_processed``
                    # is the cumulative "got past hash" count;
                    # ``files_unmatched`` rises in lockstep with
                    # files that hit no DAT entry.
                    task = asyncio.create_task(
                        report_progress(
                            sessionmaker,
                            job_run_id=context.job_run_id,
                            items_processed=_base + ev.files_seen,
                            summary_patch={
                                "total_items": _total,
                                "matched": _matched + ev.files_processed,
                                "unmatched": _unmatched
                                + ev.files_unmatched,
                            },
                        )
                    )
                    # Suppress RUF006 — fire-and-forget by design.
                    task.add_done_callback(lambda _: None)

                result = await full_scan(
                    session=session,
                    library_id=library.id,
                    library_path=library_path,
                    accepted_extensions=accepted,
                    progress_sink=_sink,
                )
                processed_files_overall += result.files_seen
                matched_overall += result.files_linked
                unmatched_overall += result.files_unmatched
                scanned += 1
                per_library.append(
                    {
                        "library_id": library.id,
                        "files_seen": result.files_seen,
                        "files_processed": result.files_processed,
                        "files_skipped": result.files_skipped,
                        "files_linked": result.files_linked,
                        "files_orphaned": result.files_orphaned,
                        "files_unmatched": result.files_unmatched,
                    }
                )

        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "libraries_scanned": scanned,
                "libraries_skipped": skipped,
                "per_library": per_library,
            },
        )


class AutoCheckAddedAdapter(_AdapterBase):
    """Event-driven; the scheduler doesn't fire it on a cron.
    The API layer calls ``trigger("AutoCheckAdded", ...)``
    when a new game is added (spec 008's importer).

    Runs one manual-search round scoped to the game's title +
    platform, then — unlike the manual modal which leaves the
    grab decision to the operator — picks the highest-scoring
    eligible candidate for THIS game and dispatches it through
    the same :func:`dispatch_winner` path RSS uses. Eligibility:
      * matched by the pipeline to the game we just added
      * ``rejection`` is None (passed every soft gate)
      * ``score_breakdown.total >= QualityProfile.auto_grab_min_score``
        (the operator's profile floor) AND ``> 0`` (cleared the
        pipeline at all)

    Without a sessionmaker we keep the legacy stub behaviour so
    the scheduler dispatch path stays exercised end-to-end."""

    def __init__(self) -> None:
        super().__init__(job_id="AutoCheckAdded")

    async def _run(self, context: JobContext) -> JobResult:
        game_id = context.parameters.get("gameId")
        sessionmaker = getattr(context, "sessionmaker", None)
        if game_id is None or sessionmaker is None:
            return JobResult(
                status=JobStatus.SUCCESS,
                summary={
                    "stub": True,
                    "gameId": game_id,
                    "reason": (
                        "no gameId"
                        if game_id is None
                        else "no sessionmaker"
                    ),
                },
            )

        from sqlalchemy import select

        from romarr.search._clients import make_indexer_client_factory
        from romarr.search.rounds._shared import (
            dispatch_best_for_game,
            load_min_score_for_game,
        )
        from romarr.search.rounds.manual import run_manual_search
        from romarr.domain.models import Game

        async with sessionmaker() as session:
            game = (
                await session.execute(
                    select(Game).where(Game.id == int(game_id))
                )
            ).scalar_one_or_none()
            if game is None:
                return JobResult(
                    status=JobStatus.SUCCESS,
                    summary={
                        "gameId": int(game_id),
                        "skipped": True,
                        "skipReason": "game_not_found",
                    },
                )

            indexer_factory = make_indexer_client_factory(session)
            try:
                report = await run_manual_search(
                    session=session,
                    query=game.title,
                    client_factory=indexer_factory,
                    platform_id=game.platform_id,
                )
            except Exception as exc:
                return JobResult(
                    status=JobStatus.SUCCESS,
                    summary={
                        "gameId": game.id,
                        "title": game.title,
                        "platformId": game.platform_id,
                        "skipped": True,
                        "skipReason": (
                            f"search_failed: {type(exc).__name__}"
                        ),
                    },
                )

            min_score = await load_min_score_for_game(session, game.id)
            dispatch_outcome = await dispatch_best_for_game(
                session,
                game_id=game.id,
                candidates=report.candidates,
                min_score=min_score,
            )

        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "gameId": game.id,
                "title": game.title,
                "platformId": game.platform_id,
                "candidates": len(report.candidates),
                "grabs": 1 if dispatch_outcome.get("dispatched") else 0,
                "best_score": dispatch_outcome.get("best_score"),
                "min_score": min_score,
                "no_grab_reason": dispatch_outcome.get("no_grab_reason"),
                "dispatch_status": dispatch_outcome.get("status"),
            },
        )


__all__ = [
    "AutoCheckAddedAdapter",
    "BackupAdapter",
    "CutoffSearchAdapter",
    "DatUpdateAdapter",
    "HealthCheckAdapter",
    "LibraryScanAdapter",
    "MissingSearchAdapter",
    "RefreshGameMetadataAdapter",
    "RssSyncAdapter",
]
