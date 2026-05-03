"""JobRunner Protocol + registry helpers (T028).

Every periodic / on-demand job in Romarr is implemented as a
``JobRunner``: an object whose ``run(context)`` coroutine accepts
a :class:`JobContext` and returns a :class:`JobResult`. The
:class:`SchedulerService` looks up the runner from a dict
keyed by ``job_id`` and awaits it; concurrency caps + audit
writes are the scheduler's concern, not the runner's.

The Protocol is structurally typed so a stub class with the
right shape passes the runtime check — useful in tests where
we don't want to reach into the real spec 004 / 007 / 011
modules just to verify dispatch.

This module also exposes :func:`build_default_registry` which
the application factory calls during lifespan startup to
assemble the production registry from the per-job adapters in
:mod:`romarr.tasks.runners.adapters`. Tests pass their own
stubbed registry instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from romarr.tasks.types import JobContext, JobResult


@runtime_checkable
class JobRunner(Protocol):
    """Structural typing — a class is a runner iff it has an
    async ``run(context: JobContext) -> JobResult``.

    Adapters typically also expose a ``job_id: str`` class
    attribute matching the row in ``job``; the registry uses it
    to keep the bind table self-describing. The Protocol doesn't
    require it (so test stubs can inline an instance), but the
    convention keeps the production wiring readable.
    """

    def run(
        self, context: JobContext
    ) -> Awaitable[JobResult]: ...


def build_default_registry(
    *,
    health_engine: Any | None = None,
) -> dict[str, JobRunner]:
    """Assemble the production runner registry from the per-job
    adapters. Imported lazily so the runtime registry isn't
    constructed at module-import time (the adapters reach into
    other specs' modules; pulling them all on import would
    double the startup cost).

    The dict is keyed by ``job.id`` matching the SEED catalogue.

    ``health_engine`` is the optional :class:`HealthEngine`
    instance the application's lifespan builds via
    :func:`romarr.notifications.health.builder.build_health_engine`.
    When provided, the ``HealthCheck`` cron periodically calls
    ``engine.refresh()`` (spec 011 T057). When ``None``, the
    HealthCheckAdapter falls back to its stub-success behaviour.
    """
    from romarr.tasks.runners.adapters import (
        AutoCheckAddedAdapter,
        BackupAdapter,
        CutoffSearchAdapter,
        DatUpdateAdapter,
        HealthCheckAdapter,
        LibraryScanAdapter,
        MissingSearchAdapter,
        RefreshGameMetadataAdapter,
        RssSyncAdapter,
    )

    return {
        "RssSync": RssSyncAdapter(),
        "CutoffSearch": CutoffSearchAdapter(),
        "MissingSearch": MissingSearchAdapter(),
        "RefreshGameMetadata": RefreshGameMetadataAdapter(),
        "DatUpdate": DatUpdateAdapter(),
        "Backup": BackupAdapter(),
        "HealthCheck": HealthCheckAdapter(engine=health_engine),
        "LibraryScan": LibraryScanAdapter(),
        "AutoCheckAdded": AutoCheckAddedAdapter(),
    }


__all__ = ["JobRunner", "build_default_registry"]
