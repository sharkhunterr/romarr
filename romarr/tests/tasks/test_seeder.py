"""Seeder tests (T013-T016, FR-008, SC-001)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.tasks.models import Job
from romarr.tasks.seeder import DEFAULT_CATALOGUE, seed_defaults

# ---------------------------------------------------------------------------
# T013 — fresh DB seeds nine documented rows (SC-001)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_boot_seeds_nine(
    async_session: AsyncSession,
) -> None:
    inserted = await seed_defaults(async_session)
    assert inserted == 9

    rows = (
        await async_session.execute(select(Job).order_by(Job.id))
    ).scalars().all()
    assert len(rows) == 9

    by_id = {row.id: row for row in rows}
    expected = {default.job_id for default in DEFAULT_CATALOGUE}
    assert set(by_id.keys()) == expected

    # Every default carries the factory-default sentinel.
    assert all(row.is_factory_default for row in rows)


@pytest.mark.asyncio
async def test_documented_schedules_match_catalogue(
    async_session: AsyncSession,
) -> None:
    """Specific cell-by-cell check against the data-model.md
    catalogue so a documented schedule change is caught here
    in addition to the seeder source."""
    await seed_defaults(async_session)
    rows = (
        await async_session.execute(select(Job))
    ).scalars().all()
    by_id = {row.id: row for row in rows}

    assert by_id["RssSync"].schedule_interval_seconds == 900
    assert by_id["RssSync"].schedule_cron is None

    assert by_id["CutoffSearch"].schedule_cron == "0 */6 * * *"
    assert by_id["MissingSearch"].schedule_cron == "0 */12 * * *"
    assert by_id["RefreshGameMetadata"].schedule_cron == "0 3 * * *"
    assert by_id["DatUpdate"].schedule_cron == "0 4 * * 0"
    assert by_id["Backup"].schedule_cron == "0 2 * * *"

    assert by_id["HealthCheck"].schedule_interval_seconds == 600
    assert by_id["LibraryScan"].schedule_interval_seconds == 3600

    # Event-driven: both schedule fields NULL.
    assert by_id["AutoCheckAdded"].schedule_cron is None
    assert by_id["AutoCheckAdded"].schedule_interval_seconds is None


# ---------------------------------------------------------------------------
# T014 — idempotent rerun
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_rerun(async_session: AsyncSession) -> None:
    """Running the seeder twice inserts nothing on the second
    pass and leaves existing rows untouched."""
    first = await seed_defaults(async_session)
    assert first == 9

    second = await seed_defaults(async_session)
    assert second == 0

    rows = (
        await async_session.execute(select(Job))
    ).scalars().all()
    assert len(rows) == 9


# ---------------------------------------------------------------------------
# T015 — operator edit preserved (FR-008)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_edit_is_preserved_across_rerun(
    async_session: AsyncSession,
) -> None:
    """Operator changes ``MissingSearch.schedule_interval_seconds``
    to 7200 (2 h instead of every 12 h cron). A subsequent
    seeder run MUST NOT revert the operator's edit."""
    await seed_defaults(async_session)

    job = (
        await async_session.execute(
            select(Job).where(Job.id == "MissingSearch")
        )
    ).scalar_one()
    job.schedule_cron = None
    job.schedule_interval_seconds = 7200
    await async_session.commit()

    inserted = await seed_defaults(async_session)
    assert inserted == 0

    refreshed = (
        await async_session.execute(
            select(Job).where(Job.id == "MissingSearch")
        )
    ).scalar_one()
    assert refreshed.schedule_interval_seconds == 7200
    assert refreshed.schedule_cron is None


# ---------------------------------------------------------------------------
# T016 — LibraryScan disabled by default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_library_scan_default_disabled(
    async_session: AsyncSession,
) -> None:
    """Operators opt in once they have libraries to scan; the
    seeder ships ``LibraryScan.enabled = False`` per the
    catalogue."""
    await seed_defaults(async_session)
    job = (
        await async_session.execute(
            select(Job).where(Job.id == "LibraryScan")
        )
    ).scalar_one()
    assert job.enabled is False


@pytest.mark.asyncio
async def test_other_defaults_are_enabled(
    async_session: AsyncSession,
) -> None:
    await seed_defaults(async_session)
    rows = (
        await async_session.execute(select(Job))
    ).scalars().all()
    enabled_ids = {row.id for row in rows if row.enabled}
    expected_enabled = {
        default.job_id
        for default in DEFAULT_CATALOGUE
        if default.enabled
    }
    assert enabled_ids == expected_enabled
    assert "LibraryScan" not in enabled_ids


# ---------------------------------------------------------------------------
# Partial-existing scenario: a future release adds a new factory default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_existing_inserts_only_missing(
    async_session: AsyncSession,
) -> None:
    """If only some defaults exist (simulating an upgrade where
    the catalogue grew), the seeder inserts only the missing
    ones — the existing rows are left alone."""
    # Pre-insert one of the documented defaults manually.
    async_session.add(
        Job(
            id="RssSync",
            name="RSS Sync",
            type="rss_sync",
            schedule_interval_seconds=900,
            enabled=True,
            is_factory_default=True,
        )
    )
    await async_session.commit()

    inserted = await seed_defaults(async_session)
    assert inserted == 8  # 9 catalogue - 1 already present

    rows = (
        await async_session.execute(select(Job))
    ).scalars().all()
    assert len(rows) == 9
