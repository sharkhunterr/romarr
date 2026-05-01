"""Factory-default job catalogue (FR-008, SC-001).

On first boot, ``seed_defaults(session)`` inserts the nine
documented default jobs into ``job``. The catalogue mirrors
``data-model.md``'s "Default Job Catalogue" section
verbatim — keeping the source of truth co-located with the spec
so a documented schedule change is one diff.

The seeder is **idempotent** in two senses:

  * If a default job already exists in the table, the seeder
    leaves it alone — re-runs are no-ops (FR-008 second
    sentence).
  * If an operator edited a default's schedule (detected by
    ``created_at != updated_at``), the seeder preserves the
    operator's value rather than reverting (FR-008 third
    sentence).

Edit detection follows the spec 006 pattern: SQLAlchemy's
``TimestampMixin`` writes ``updated_at`` on every UPDATE, while
``created_at`` is set once on INSERT and never changed. So a
row whose ``updated_at > created_at`` has been edited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from romarr.tasks.models import Job

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


JobType = Literal[
    "rss_sync",
    "cutoff_search",
    "missing_search",
    "refresh_metadata",
    "dat_update",
    "backup",
    "health_check",
    "library_scan",
    "auto_check_added",
    "custom",
]


@dataclass(frozen=True)
class _DefaultJob:
    """One entry in the factory catalogue. ``cron`` and
    ``interval_seconds`` are mutually exclusive (the
    ``auto_check_added`` event-driven row sets neither)."""

    job_id: str
    name: str
    type: JobType
    cron: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True


# The catalogue from ``specs/012-tasks-scheduler/data-model.md``.
# Order matches the spec table for grep-ability.
DEFAULT_CATALOGUE: tuple[_DefaultJob, ...] = (
    _DefaultJob(
        job_id="RssSync",
        name="RSS Sync",
        type="rss_sync",
        interval_seconds=900,
    ),
    _DefaultJob(
        job_id="CutoffSearch",
        name="Cutoff Search",
        type="cutoff_search",
        cron="0 */6 * * *",
    ),
    _DefaultJob(
        job_id="MissingSearch",
        name="Missing Search",
        type="missing_search",
        cron="0 */12 * * *",
    ),
    _DefaultJob(
        job_id="RefreshGameMetadata",
        name="Refresh Game Metadata",
        type="refresh_metadata",
        cron="0 3 * * *",
    ),
    _DefaultJob(
        job_id="DatUpdate",
        name="DAT Update",
        type="dat_update",
        cron="0 4 * * 0",
    ),
    _DefaultJob(
        job_id="Backup",
        name="Backup",
        type="backup",
        cron="0 2 * * *",
    ),
    _DefaultJob(
        job_id="HealthCheck",
        name="Health Check",
        type="health_check",
        interval_seconds=600,
    ),
    _DefaultJob(
        job_id="LibraryScan",
        name="Library Scan",
        type="library_scan",
        interval_seconds=3600,
        # Off by default — operators opt in once they have
        # libraries to scan.
        enabled=False,
    ),
    _DefaultJob(
        job_id="AutoCheckAdded",
        name="Auto-Check Added",
        type="auto_check_added",
        # Event-driven: both schedule fields NULL.
    ),
)


async def seed_defaults(session: AsyncSession) -> int:
    """Insert any missing factory-default jobs. Returns the
    number of rows inserted (zero on subsequent boots).

    The function does NOT touch existing rows — operator edits
    survive every reboot, and a new factory default added in
    a future release lands on the next seeder run.
    """
    existing_ids = {
        row[0]
        for row in (
            await session.execute(select(Job.id))
        ).all()
    }
    inserted = 0
    for default in DEFAULT_CATALOGUE:
        if default.job_id in existing_ids:
            continue
        session.add(
            Job(
                id=default.job_id,
                name=default.name,
                type=default.type,
                schedule_cron=default.cron,
                schedule_interval_seconds=default.interval_seconds,
                enabled=default.enabled,
                is_factory_default=True,
            )
        )
        inserted += 1
    if inserted:
        await session.commit()
    return inserted


__all__ = ["DEFAULT_CATALOGUE", "seed_defaults"]
