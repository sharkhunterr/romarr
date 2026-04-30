"""Audit-log lifecycle helpers (T031, FR-023, FR-024).

Each pack-apply attempt produces exactly one
:class:`PlatformPackApplicationLog` row. Successful runs mark the
row as ``status='success'``; failed runs persist the row even though
the data side rolls back (FR-024). The ``fail_log`` helper deliberately
opens its **own** session because the parent ingest transaction has
already rolled back at fail time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from romarr.platform_packs.models import PlatformPackApplicationLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def start_log(
    session: AsyncSession,
    *,
    pack_version: str,
    applied_by: str,
) -> PlatformPackApplicationLog:
    """Insert an in-progress log row inside the ingestor transaction.

    The row's ``finished_at`` is left NULL until completion. ``action``
    is initially ``"applied"`` — the ingestor patches it to
    ``"reapplied"`` / ``"skipped"`` before commit if needed.
    """
    row = PlatformPackApplicationLog(
        pack_version=pack_version,
        action="applied",
        platforms_affected=[],
        parsing_strategies_affected=[],
        started_at=datetime.now(UTC),
        status="success",
        applied_by=applied_by,
    )
    session.add(row)
    await session.flush()
    return row


async def complete_log(
    session: AsyncSession,
    row: PlatformPackApplicationLog,
    *,
    action: str,
    platforms_affected: list[str],
    parsing_strategies_affected: list[str],
) -> None:
    """Mark a log row as finished + successful, in the same session."""
    row.action = action
    row.platforms_affected = list(platforms_affected)
    row.parsing_strategies_affected = list(parsing_strategies_affected)
    row.finished_at = datetime.now(UTC)
    row.status = "success"
    await session.flush()


async def fail_log(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    pack_version: str,
    applied_by: str,
    started_at: datetime,
    error_message: str,
) -> None:
    """Persist a ``status='failed'`` row in a SEPARATE session.

    The ingestor's main transaction has rolled back when this is
    called, so the log row needs its own session that commits
    independently of any user data.
    """
    async with sessionmaker() as session:
        session.add(
            PlatformPackApplicationLog(
                pack_version=pack_version,
                action="failed",
                platforms_affected=[],
                parsing_strategies_affected=[],
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status="failed",
                error_message=error_message,
                applied_by=applied_by,
            )
        )
        await session.commit()
