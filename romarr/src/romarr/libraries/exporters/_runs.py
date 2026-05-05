"""Per-(library, exporter) emission-tracking upsert helper.

Both the orchestrator's per-import dispatch and the manual-run
endpoint call into :func:`record_exporter_run` after a write
attempt so the operator UI can surface "last successful emit"
+ "total emissions" per library + exporter (FR-019 / T077).

Status semantics:
    * ``ok``        — the writer wrote the file;
    * ``coalesced`` — another writer held the advisory lock so this
      emission was a no-op (FR-017a);
    * ``error``     — the renderer or writer raised; ``last_error``
      carries the diagnostic message.

The helper is **best-effort**: a failure to record the run never
invalidates the actual emission, so callers wrap it with their own
try/except guard.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from romarr.libraries.models import LibraryExporterRun

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_RunStatus = Literal["ok", "coalesced", "error"]


async def record_exporter_run(
    *,
    session: AsyncSession,
    library_id: int,
    exporter_name: str,
    status: _RunStatus,
    error: str | None = None,
    now: datetime | None = None,
) -> LibraryExporterRun:
    """Upsert a :class:`LibraryExporterRun` row.

    Returns the persisted row (refreshed) so callers can surface
    its updated counters in API responses.
    """
    when = now or datetime.now(UTC)

    row = (
        await session.execute(
            select(LibraryExporterRun).where(
                LibraryExporterRun.library_id == library_id,
                LibraryExporterRun.exporter_name == exporter_name,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = LibraryExporterRun(
            library_id=library_id,
            exporter_name=exporter_name,
            last_run_at=when,
            run_count=1,
            last_status=status,
            last_error=error if status == "error" else None,
        )
        session.add(row)
    else:
        row.last_run_at = when
        row.run_count += 1
        row.last_status = status
        row.last_error = error if status == "error" else None
    await session.commit()
    await session.refresh(row)
    return row


__all__ = ["record_exporter_run"]
