"""Round-trip tests for ParsingStrategy + PlatformPackApplicationLog (T008)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import PlatformPack
from romarr.platform_packs.models import (
    ParsingStrategy,
    PlatformPackApplicationLog,
)


async def test_parsing_strategy_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        ParsingStrategy(
            id="ines-header",
            name="iNES Header Reader",
            pattern=r"^NES\x1A",
            apply_to_platforms=["nes"],
            pack_version="2026.04.001",
            pack_source="builtin",
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(ParsingStrategy).where(ParsingStrategy.id == "ines-header")
        )
    ).scalar_one()
    assert row.pattern == r"^NES\x1A"
    assert row.apply_to_platforms == ["nes"]
    assert row.pack_source == "builtin"


async def test_application_log_round_trip(
    async_session: AsyncSession,
) -> None:
    pack = PlatformPack(
        pack_version="2026.04.099",
        schema_version=1,
        contents_hash="0" * 64,
        pack_source="community",
        applied_at=datetime.now(UTC),
    )
    async_session.add(pack)
    await async_session.flush()

    started = datetime.now(UTC)
    async_session.add(
        PlatformPackApplicationLog(
            pack_version="2026.04.099",
            action="applied",
            platforms_affected=["nes", "snes"],
            parsing_strategies_affected=["ines-header"],
            started_at=started,
            finished_at=started,
            status="success",
            applied_by="system",
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(PlatformPackApplicationLog).where(
                PlatformPackApplicationLog.pack_version == "2026.04.099"
            )
        )
    ).scalar_one()
    assert row.action == "applied"
    assert row.platforms_affected == ["nes", "snes"]
    assert row.parsing_strategies_affected == ["ines-header"]
    assert row.status == "success"
