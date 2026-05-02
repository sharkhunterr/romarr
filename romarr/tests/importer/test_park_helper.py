"""Tests for the unidentified-park helper (slice 79).

Three scenarios:
  * First park inserts a new row with attempt_count=1.
  * Re-park for the same path UPDATEs the existing row,
    bumps attempt_count, refreshes rejection_reason +
    last_attempt_at while preserving discovered_at.
  * Hint fields (suggested_platform_id, suggested_game_id,
    library_id, hashes) round-trip correctly and only
    overwrite when the caller passes non-None.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform, UnidentifiedDump
from romarr.importer._park import park_in_unidentified


@pytest.mark.asyncio
async def test_first_park_inserts_new_row(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    src = tmp_path / "downloads" / "unknown.zip"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x" * 4096)

    row = await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=4096,
        rejection_reason="match:no_game",
        sha1="a" * 40,
    )
    await async_session.commit()

    assert row.id > 0
    assert row.path == str(src)
    assert row.attempt_count == 1
    assert row.rejection_reason == "match:no_game"
    assert row.sha1 == "a" * 40
    assert row.discovered_at is not None
    assert row.last_attempt_at is not None
    assert row.size_bytes == 4096


@pytest.mark.asyncio
async def test_re_park_updates_existing_row_and_bumps_count(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    src = tmp_path / "downloads" / "unknown.zip"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x" * 4096)

    first = await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=4096,
        rejection_reason="match:no_game",
    )
    await async_session.commit()
    discovered_at = first.discovered_at
    first_id = first.id

    # Force a wall-clock gap so last_attempt_at moves forward.
    later = datetime.now(UTC) + timedelta(milliseconds=10)

    second = await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=4096,
        rejection_reason="extract:bomb-detected",
        last_error="archive expanded past the cap",
    )
    await async_session.commit()

    assert second.id == first_id  # same row, updated in place
    assert second.attempt_count == 2
    assert second.discovered_at == discovered_at  # original time preserved
    assert second.last_attempt_at >= later - timedelta(seconds=1)
    assert second.rejection_reason == "extract:bomb-detected"
    assert second.last_error == "archive expanded past the cap"

    # Verify the unique-on-path constraint stayed satisfied —
    # only one row for the given path.
    rows = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(src))
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_re_park_does_not_overwrite_hashes_when_none_passed(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Caller-provided hints survive across re-parks: the
    second call without hashes keeps the originally-recorded
    sha1, but a fresh rejection_reason still wins."""
    src = tmp_path / "downloads" / "unknown.zip"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x")

    await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=1,
        rejection_reason="match:no_game",
        sha1="a" * 40,
        crc32="deadbeef",
    )
    await async_session.commit()

    # Re-park: caller knows the new reason but passes no hashes.
    row = await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=1,
        rejection_reason="extract:bad-archive",
    )
    await async_session.commit()

    assert row.sha1 == "a" * 40  # preserved
    assert row.crc32 == "deadbeef"  # preserved
    assert row.rejection_reason == "extract:bad-archive"  # refreshed


@pytest.mark.asyncio
async def test_park_records_suggested_game_and_platform(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the orchestrator knows the operator's intended game
    (e.g. spec 008's destination-collision branch), the hints
    should land on the row so the manual-triage UI can render
    "park, but Romarr suspects this is X"."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.flush()
    game = Game(
        platform_id=platform.id,
        slug="sonic",
        title="Sonic the Hedgehog",
    )
    async_session.add(game)
    await async_session.flush()

    src = tmp_path / "downloads" / "sonic_with_collision.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x")

    row = await park_in_unidentified(
        session=async_session,
        source_path=src,
        size_bytes=1,
        rejection_reason="destination_collision",
        suggested_platform_id=platform.id,
        suggested_game_id=game.id,
    )
    await async_session.commit()

    assert row.suggested_platform_id == platform.id
    assert row.suggested_game_id == game.id
    assert row.rejection_reason == "destination_collision"
