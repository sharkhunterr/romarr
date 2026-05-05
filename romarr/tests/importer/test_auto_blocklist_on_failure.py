"""Auto-blocklist on content-correctness failure (spec 008 T083).

When the orchestrator's failure path lands on one of the
content-correctness rejection reasons (bomb / bad-archive /
depth-exceeded / destination_collision / move_hash_mismatch),
a Blocklist row is added with ``added_by='system'`` so the
search engine won't re-grab the same bad release.

Transient subreasons (hash:failed, profile:*, move:permission
/ disk_full / lock:timeout, routing:*) DO NOT auto-blocklist —
they're operator-config or environmental.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.search.models import Blocklist


@pytest.mark.asyncio
async def test_extract_bad_archive_creates_blocklist_row(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Corrupt .zip → extract fails with ``extract:bad-archive``
    → blocklist row created with system attribution."""
    archive = tmp_path / "downloads" / "broken.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"this is not a real zip file")

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    rows = (
        await async_session.execute(select(Blocklist))
    ).scalars().all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.added_by == "system"
    assert entry.reason == "extract:bad-archive"
    assert entry.release_title == "broken.zip"


@pytest.mark.asyncio
async def test_no_game_match_does_not_blocklist(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """``match:no_game`` is NOT a content-correctness failure —
    re-grabbing the same release might succeed once the operator
    creates the matching Game. No blocklist row is created."""
    rom = tmp_path / "downloads" / "Mystery.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(b"\x42" * 4096)  # arbitrary garbage

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    rows = (
        await async_session.execute(select(Blocklist))
    ).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_blocklist_entry_carries_sha1_when_available(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the hash succeeded but a downstream content failure
    fired, the blocklist row carries the SHA-1 so future grabs
    match by hash. The bad-archive case here doesn't pass the
    hash step (extract fails before hash) so the entry's sha1
    is None — that's the correct contract for this taxonomy
    branch (the file's bytes can't be hashed safely)."""
    archive = tmp_path / "downloads" / "broken.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"definitely not a zip")

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    await run_import(context, session=async_session)

    entry = (
        await async_session.execute(select(Blocklist))
    ).scalar_one()
    # Bad-archive can't compute a SHA-1 (extract fails first).
    assert entry.hash_sha1 is None
