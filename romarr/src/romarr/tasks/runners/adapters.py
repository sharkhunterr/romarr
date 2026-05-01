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
    refresh; without it, refreshes the full library batch."""

    def __init__(self) -> None:
        super().__init__(job_id="RefreshGameMetadata")

    async def _run(self, context: JobContext) -> JobResult:
        game_id = context.parameters.get("gameId")
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "stub": True,
                "scope": "single-game" if game_id else "all-games",
                "gameId": game_id,
            },
        )


class DatUpdateAdapter(_AdapterBase):
    """Wraps the DAT pack auto-refresh."""

    def __init__(self) -> None:
        super().__init__(job_id="DatUpdate")


class BackupAdapter(_AdapterBase):
    """Wraps the backup runner — backs up the DB + config to
    ``<data>/backups/`` per FR-027a."""

    def __init__(self) -> None:
        super().__init__(job_id="Backup")


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
    when a new game is added (spec 008's importer)."""

    def __init__(self) -> None:
        super().__init__(job_id="AutoCheckAdded")

    async def _run(self, context: JobContext) -> JobResult:
        game_id = context.parameters.get("gameId")
        return JobResult(
            status=JobStatus.SUCCESS,
            summary={
                "stub": True,
                "gameId": game_id,
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
