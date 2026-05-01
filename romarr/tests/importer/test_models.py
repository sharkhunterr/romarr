"""ImportHistory model tests (T011)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.importer.models import ImportHistory


def _row(**overrides: object) -> ImportHistory:
    base: dict[str, object] = {
        "source_path": "/downloads/sonic.zip",
        "imported_via": "manual",
        "success": True,
        "correlation_id": str(uuid4()),
        "started_at": datetime.now(UTC),
    }
    base.update(overrides)
    return ImportHistory(**base)  # type: ignore[arg-type]


async def test_round_trip(async_session: AsyncSession) -> None:
    row = _row(
        dest_path="/library/megadrive/Sonic.md",
        source_hash_sha1="a" * 40,
        confidence=0.95,
        imported_by="alice",
        finished_at=datetime.now(UTC),
        duration_ms=1234,
    )
    async_session.add(row)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == row.id)
        )
    ).scalar_one()
    assert fetched.imported_via == "manual"
    assert fetched.success is True
    assert fetched.coalesced is False  # default
    assert fetched.dest_path == "/library/megadrive/Sonic.md"
    assert float(fetched.confidence) == pytest.approx(0.95)
    assert fetched.duration_ms == 1234


async def test_imported_via_check_rejects_unknown(
    async_session: AsyncSession,
) -> None:
    async_session.add(_row(imported_via="bogus"))
    with pytest.raises(IntegrityError):
        await async_session.commit()


async def test_nullable_fk_columns(async_session: AsyncSession) -> None:
    """Every FK on the audit row must accept NULL — the importer
    records failures even when the game / release / dump don't
    exist yet."""
    row = _row(success=False, error_msg="extract:bad-archive")
    async_session.add(row)
    await async_session.commit()
    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == row.id)
        )
    ).scalar_one()
    assert fetched.game_id is None
    assert fetched.release_id is None
    assert fetched.dump_id is None
    assert fetched.download_client_id is None
    assert fetched.error_msg == "extract:bad-archive"


async def test_coalesced_marker_round_trips(
    async_session: AsyncSession,
) -> None:
    row = _row(coalesced=True)
    async_session.add(row)
    await async_session.commit()
    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == row.id)
        )
    ).scalar_one()
    assert fetched.coalesced is True
    assert fetched.success is True


async def test_unidentified_dump_extension_columns_persist(
    async_session: AsyncSession,
) -> None:
    """The three new columns added by spec 008 (``rejection_reason``,
    ``library_id``, ``suggested_game_id``) round-trip through the
    foundation's ``UnidentifiedDump`` ORM class."""
    from romarr.domain.models import UnidentifiedDump

    row = UnidentifiedDump(
        path="/dl/unknown.zip",
        size_bytes=1024,
        discovered_at=datetime.now(UTC),
        rejection_reason="match:no_game",
    )
    async_session.add(row)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.id == row.id)
        )
    ).scalar_one()
    assert fetched.rejection_reason == "match:no_game"
    assert fetched.library_id is None
    assert fetched.suggested_game_id is None
