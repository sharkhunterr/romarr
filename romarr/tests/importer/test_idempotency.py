"""Tests for the coalesce-check helper (slice 81)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Dump, Game, Platform, Release
from romarr.importer._idempotency import find_existing_dump


async def _seed_dump(
    session: AsyncSession,
    *,
    sha1: str,
    suffix: str = "",
) -> tuple[int, int]:
    """Seed Platform → Game → Release → Dump and return
    (release_id, dump_id)."""
    platform = Platform(slug=f"md-{uuid4().hex[:6]}", name="Mega Drive")
    session.add(platform)
    await session.flush()
    game = Game(
        platform_id=platform.id,
        slug=f"sonic-{uuid4().hex[:6]}",
        title="Sonic the Hedgehog",
    )
    session.add(game)
    await session.flush()
    release = Release(
        game_id=game.id,
        name=f"Sonic the Hedgehog (USA){suffix}",
    )
    session.add(release)
    await session.flush()
    dump = Dump(
        release_id=release.id,
        path=f"/library/megadrive/Sonic_{uuid4().hex}.md",
        original_filename="Sonic the Hedgehog (USA).md",
        size_bytes=524288,
        format="md",
        crc32="d3578bf6",
        md5="d" * 32,
        sha1=sha1,
    )
    session.add(dump)
    await session.flush()
    return release.id, dump.id


@pytest.mark.asyncio
async def test_find_existing_dump_returns_match(
    async_session: AsyncSession,
) -> None:
    sha1 = "a" * 40
    release_id, dump_id = await _seed_dump(async_session, sha1=sha1)
    await async_session.commit()

    found = await find_existing_dump(
        session=async_session, sha1=sha1, release_id=release_id
    )
    assert found is not None
    assert found.id == dump_id


@pytest.mark.asyncio
async def test_find_existing_dump_case_insensitive(
    async_session: AsyncSession,
) -> None:
    """Caller can pass mixed-case SHA-1; the helper normalises
    to lowercase before the lookup so the canonical lower-case
    Dump.sha1 still matches."""
    sha1 = "a" * 40  # persisted as lowercase
    release_id, dump_id = await _seed_dump(async_session, sha1=sha1)
    await async_session.commit()

    found = await find_existing_dump(
        session=async_session,
        sha1=sha1.upper(),  # mixed case input
        release_id=release_id,
    )
    assert found is not None
    assert found.id == dump_id


@pytest.mark.asyncio
async def test_find_existing_dump_returns_none_when_no_release_match(
    async_session: AsyncSession,
) -> None:
    """Same SHA-1, different release_id → no coalesce. The
    orchestrator's destination-collision branch handles this
    case downstream."""
    sha1 = "a" * 40
    other_release_id, _ = await _seed_dump(async_session, sha1=sha1)
    await async_session.commit()

    # Use a release_id that doesn't have a Dump with this sha1.
    found = await find_existing_dump(
        session=async_session,
        sha1=sha1,
        release_id=other_release_id + 1_000_000,
    )
    assert found is None


@pytest.mark.asyncio
async def test_find_existing_dump_returns_none_when_no_sha1_match(
    async_session: AsyncSession,
) -> None:
    """Same release_id, different SHA-1 → no coalesce. The
    orchestrator proceeds with the new dump (potential upgrade
    path)."""
    persisted_sha1 = "a" * 40
    release_id, _ = await _seed_dump(async_session, sha1=persisted_sha1)
    await async_session.commit()

    found = await find_existing_dump(
        session=async_session,
        sha1="b" * 40,
        release_id=release_id,
    )
    assert found is None


@pytest.mark.asyncio
async def test_find_existing_dump_empty_db(
    async_session: AsyncSession,
) -> None:
    found = await find_existing_dump(
        session=async_session, sha1="c" * 40, release_id=1
    )
    assert found is None
