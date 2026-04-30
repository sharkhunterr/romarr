"""Parsing-strategies upsert tests (T027, FR-014)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.platform_packs import IngestSource, ingest_pack
from romarr.platform_packs.models import ParsingStrategy


def _community() -> IngestSource:
    return IngestSource(pack_source="community", applied_by="alice")


_PACK_WITH_STRATEGIES = (
    b"pack_version: '2026.05.001'\n"
    b"schema_version: 1\n"
    b"parsing_strategies:\n"
    b"  - id: ines-header\n    description: 'iNES header'\n"
    b"    regex: '^NES\\\\x1A'\n"
    b"  - id: snes-header\n    description: 'SNES header'\n"
    b"    regex: '^.{0,512}SUPER'\n"
    b"platforms:\n"
    b"  - slug: nes\n    name: NES\n    manufacturer: Nintendo\n"
    b"    formats:\n      - extension: '.nes'\n        format_type: cartridge\n"
)


@pytest.mark.asyncio
async def test_pack_inserts_strategies(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    sm = async_sessionmaker_factory
    async with sm() as s:
        result = await ingest_pack(
            s, sessionmaker=sm, content=_PACK_WITH_STRATEGIES, source=_community()
        )
    assert sorted(result.parsing_strategies_affected) == [
        "ines-header",
        "snes-header",
    ]

    async with sm() as s:
        rows = (
            (await s.execute(select(ParsingStrategy)))
            .scalars()
            .all()
        )
    assert {r.id for r in rows} == {"ines-header", "snes-header"}
    assert all(r.pack_source == "community" for r in rows)


@pytest.mark.asyncio
async def test_user_overridden_strategy_is_preserved(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A user-overridden strategy survives a pack apply that defines
    the same id with a different pattern."""
    sm = async_sessionmaker_factory
    async with sm() as s:
        s.add(
            ParsingStrategy(
                id="ines-header",
                name="Operator's iNES",
                pattern=r"^OPERATOR-PATTERN",
                apply_to_platforms=[],
                pack_version=None,
                pack_source="user",
            )
        )
        await s.commit()

    async with sm() as s:
        await ingest_pack(
            s, sessionmaker=sm, content=_PACK_WITH_STRATEGIES, source=_community()
        )

    async with sm() as s:
        ines = (
            await s.execute(
                select(ParsingStrategy).where(ParsingStrategy.id == "ines-header")
            )
        ).scalar_one()
        snes = (
            await s.execute(
                select(ParsingStrategy).where(ParsingStrategy.id == "snes-header")
            )
        ).scalar_one()

    # User strategy untouched; sibling community strategy upserted.
    assert ines.pattern == "^OPERATOR-PATTERN"
    assert ines.pack_source == "user"
    assert snes.pattern == "^.{0,512}SUPER"
    assert snes.pack_source == "community"
