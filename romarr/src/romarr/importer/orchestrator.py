"""Importer orchestrator — the 13-step pipeline driver (spec 008).

Slice 1 ships the SCAF only: every pipeline step raises
:class:`NotImplementedError`. Subsequent slices (WATCH, EXTRACT,
HASH, DATMATCH, IDENTIFY, GAMEMATCH, MULTIDISC, PROFILEGATE,
RENDER, MOVE, DBUPDATE, LIFECYCLE, NOTIFY) fill in their step.

The driver lives here so the pipeline shape is a single
readable function — it threads :class:`ImportContext` through
each step, building up the working state. Every step is async so
the orchestrator stays cancellable end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.importer.types import ImportContext, ImportOutcome


_NOT_IMPLEMENTED_MSG = (
    "{step} not implemented yet — lands with the {phase} slice"
)


async def run_import(context: ImportContext) -> ImportOutcome:
    """Run the 13-step import pipeline against ``context``.

    Returns the :class:`ImportOutcome` covering the audit row that
    was produced. Raises only for programmer errors (truly
    unexpected failures); domain failures are surfaced as
    ``ImportOutcome(success=False)`` so the caller can record the
    audit and dispatch lifecycle / notify steps regardless.
    """
    raise NotImplementedError(
        _NOT_IMPLEMENTED_MSG.format(step="run_import", phase="WATCH")
    )


async def start_watcher() -> None:
    """Spawn the polling watcher background task (FR-001).
    Wired into the application lifespan."""
    raise NotImplementedError(
        _NOT_IMPLEMENTED_MSG.format(step="start_watcher", phase="WATCH")
    )


async def stop_watcher() -> None:
    """Cancel the polling watcher background task on shutdown."""
    raise NotImplementedError(
        _NOT_IMPLEMENTED_MSG.format(step="stop_watcher", phase="WATCH")
    )


__all__ = ["run_import", "start_watcher", "stop_watcher"]
