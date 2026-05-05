"""Manual-import bulk tests (spec 009 T068, T069, T070)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.importer.models import ImportHistory
from romarr.libraries.manual_import import (
    ManualImportRequest,
    bulk_import,
)


@pytest.mark.asyncio
async def test_bulk_under_30s(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """T068 — 50 files import in under 30 s (SC-008).

    The orchestrator's audit-only path hashes + parks each file;
    the per-entry session+commit cost is what dominates. The
    30 s budget covers the full happy path landing later;
    today's audit-only is comfortably under.
    """
    folder = tmp_path / "bulk"
    folder.mkdir()
    entries = []
    for i in range(50):
        path = folder / f"rom-{i:02d}.md"
        path.write_bytes(b"\x00" * 256)
        entries.append(ManualImportRequest(path=path, action="import"))

    started = time.perf_counter()
    results = await bulk_import(
        sessionmaker=async_sessionmaker_factory,
        entries=entries,
    )
    elapsed = time.perf_counter() - started
    assert len(results) == 50
    assert elapsed < 30.0
    # Every entry produced a history row.
    for result in results:
        assert result.history_id is not None


@pytest.mark.asyncio
async def test_skip_action_recorded(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """T069 — entries with ``action='skip'`` produce a successful
    skip outcome and DON'T invoke the orchestrator."""
    folder = tmp_path / "skip"
    folder.mkdir()
    path = folder / "rom.md"
    path.write_bytes(b"\x00" * 256)

    before = (
        await async_session.execute(select(ImportHistory))
    ).scalars().all()

    results = await bulk_import(
        sessionmaker=async_sessionmaker_factory,
        entries=[ManualImportRequest(path=path, action="skip")],
    )
    assert len(results) == 1
    assert results[0].action == "skip"
    assert results[0].success is True
    assert results[0].history_id is None  # skip never writes history

    # No new history row landed.
    after = (
        await async_session.execute(select(ImportHistory))
    ).scalars().all()
    assert len(after) == len(before)


@pytest.mark.asyncio
async def test_routing_check_per_entry(
    async_sessionmaker_factory: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """T070 — per-entry isolation: when one entry's path is bad
    (e.g., a missing file) the rest of the batch still runs.

    The orchestrator's audit-only path tolerates missing files
    (writes a failure history row instead of raising) so the
    routing check fires per entry without dropping the batch.
    """
    folder = tmp_path / "routing"
    folder.mkdir()
    good = folder / "good.md"
    good.write_bytes(b"\x00" * 256)
    missing = folder / "missing.md"  # not created on disk

    results = await bulk_import(
        sessionmaker=async_sessionmaker_factory,
        entries=[
            ManualImportRequest(path=good, action="import"),
            ManualImportRequest(path=missing, action="import"),
        ],
    )
    assert len(results) == 2
    # Both produced an outcome (the audit-only orchestrator
    # writes a history row even for missing files).
    assert results[0].history_id is not None
    assert results[1].history_id is not None
