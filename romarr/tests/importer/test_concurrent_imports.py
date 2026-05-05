"""Idempotent + concurrent-import coalescing (spec 008 T082 / FR-033 / SC-007).

The orchestrator's auto-import path is idempotent on
``(release_id, sha1)``: re-importing the same file for the same
Release produces exactly one Dump row + N coalesced history
rows. Slice 314 added an IntegrityError + recover handler so
real concurrent races also resolve to coalesced outcomes.

Note: SQLite ``:memory:`` doesn't share state across distinct
connections, so the per-tick concurrency picture in tests is
"sequential single-session writes" rather than "real parallel
inserts". Production PostgreSQL deployments hit the same
recover path on real concurrency. The sequential test below
is what pins the SC-007 idempotency contract today.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_5_sequential_runs_coalesce_to_one_dump(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """T082 — Re-running ``run_import`` 5 times against the same
    file + Release produces exactly 1 Dump and 5 history rows
    (the first creates the Dump; the next 4 coalesce per
    FR-033)."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-coalesce",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    outcomes = []
    for _ in range(5):
        context = ImportContext(
            source_path=rom,
            correlation_id=uuid4(),
            imported_via="manual",
        )
        outcomes.append(await run_import(context, session=async_session))

    # All 5 succeeded; the first inserts the Dump, the next 4
    # coalesce.
    assert all(o.success for o in outcomes)
    assert outcomes[0].coalesced is False
    coalesced_count = sum(1 for o in outcomes[1:] if o.coalesced)
    assert coalesced_count == 4

    # Exactly one Dump row.
    dumps = (
        await async_session.execute(
            select(Dump).where(Dump.release_id == release.id)
        )
    ).scalars().all()
    assert len(dumps) == 1
    # Same dump_id across all outcomes.
    assert all(o.dump_id == dumps[0].id for o in outcomes)

    # 5 history rows recorded (audit trail of every attempt).
    history_rows = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.release_id == release.id
            )
        )
    ).scalars().all()
    assert len(history_rows) == 5
    assert all(h.success for h in history_rows)
    coalesced_history = [h for h in history_rows if h.coalesced]
    assert len(coalesced_history) == 4

    # Release stays in imported state — re-runs don't take it
    # back to wanted.
    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed.status == "imported"
