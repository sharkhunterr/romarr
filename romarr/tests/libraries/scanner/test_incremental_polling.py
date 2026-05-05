"""End-to-end polling-observer integration test (spec 009 T046).

Where ``test_incremental.py`` exercises the scanner's handlers
directly, this test runs the scanner under its real watchdog
:class:`PollingObserver` so the observer-thread → asyncio-loop
dispatch is exercised. The polling cadence is dialled down to
0.1 s so the test still completes in well under the SC-004
budget (5 s for a new file to surface).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.libraries.models import Library
from romarr.libraries.scanner.incremental import IncrementalScanner

from tests.libraries.scanner.test_full_scan import _seed_minimal_profiles


@pytest.mark.asyncio
async def test_polling_observer_picks_up_new_file_within_budget(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """T046 / SC-004 — a new file dropped under ``library_path``
    fires the ``on_unmatched`` callback within 5 seconds when the
    scanner runs under :class:`PollingObserver`.

    Configures the scanner with ``observer_kind="polling"`` and a
    short debounce so the polling cadence isn't gated by a
    long quiet period."""
    library_root = tmp_path / "library"
    library_root.mkdir()

    profile_ids = await _seed_minimal_profiles(async_session)
    library = Library(
        name="Cartridges-poll",
        path=str(library_root),
        quality_profile_id=profile_ids["quality"],
        region_profile_id=profile_ids["region"],
        dump_profile_id=profile_ids["dump"],
        language_profile_id=profile_ids["language"],
        naming_profile_id=profile_ids["naming"],
    )
    async_session.add(library)
    await async_session.commit()
    await async_session.refresh(library)

    surfaced: asyncio.Future[Path] = asyncio.get_running_loop().create_future()

    async def _on_unmatched(path: Path) -> None:
        if not surfaced.done():
            surfaced.set_result(path)

    scanner = IncrementalScanner(
        sessionmaker=async_sessionmaker_factory,
        library_id=library.id,
        library_path=library_root,
        accepted_extensions={".md"},
        on_unmatched=_on_unmatched,
        debounce_seconds=0.1,
        observer_kind="polling",
    )
    await scanner.start()
    try:
        # Drop a new ROM file outside the library root first, then
        # move it in — landing it via a single rename ensures the
        # polling observer sees one snapshot delta rather than
        # racing the writer.
        rom_path = library_root / "Mystery (USA).md"
        rom_path.write_bytes(b"\x00" * 4096)

        path = await asyncio.wait_for(surfaced, timeout=5.0)
        assert path.name == "Mystery (USA).md"
    finally:
        await scanner.stop()
