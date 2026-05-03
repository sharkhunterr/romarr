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
    """Wraps spec 004's RSS sync — returns stub until the
    indexer module exposes a ``sync_all_enabled_indexers()``."""

    def __init__(self) -> None:
        super().__init__(job_id="RssSync")


class CutoffSearchAdapter(_AdapterBase):
    """Wraps spec 007's cutoff search — returns stub until the
    search module exposes a ``run_cutoff_search()``."""

    def __init__(self) -> None:
        super().__init__(job_id="CutoffSearch")


class MissingSearchAdapter(_AdapterBase):
    """Wraps spec 007's missing search."""

    def __init__(self) -> None:
        super().__init__(job_id="MissingSearch")


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
        async with sessionmaker() as session:
            result = await refresh_all_metadata(
                session,
                platform_id=platform_id,
                force=force,
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
    """Wraps spec 009's library scanners.

    The library_id parameter selects per-library scanning;
    without it, every library is scanned. Cross-spec wiring
    lands when spec 009 exposes a ``scan_full(library_id=None)``
    entry that the adapter can call directly."""

    def __init__(self) -> None:
        super().__init__(job_id="LibraryScan")

    async def _run(self, context: JobContext) -> JobResult:
        library_id = context.parameters.get("libraryId")
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "stub": True,
                "scope": (
                    f"library_id={library_id}"
                    if library_id
                    else "all-libraries"
                ),
            },
        )


class AutoCheckAddedAdapter(_AdapterBase):
    """Event-driven; the scheduler doesn't fire it on a cron.
    The API layer calls ``trigger("AutoCheckAdded", ...)``
    when a new game is added (spec 008's importer).

    Slice 181 / spec 012 T052: when the JobContext supplies a
    sessionmaker we delegate to :func:`run_search_on_add`,
    which loads the Game, runs one manual search round, and
    reports candidate / grab counts. Without a sessionmaker
    we keep the legacy stub behaviour so the scheduler dispatch
    path stays exercised end-to-end.
    """

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

        from romarr.tasks.runners.auto_check_added import (
            run_search_on_add,
        )

        async with sessionmaker() as session:
            result = await run_search_on_add(
                session, game_id=int(game_id)
            )
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "gameId": result.game_id,
                "title": result.title,
                "platformId": result.platform_id,
                "candidates": result.candidates,
                "grabs": result.grabs,
                "skipped": result.skipped,
                "skipReason": result.skip_reason,
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
