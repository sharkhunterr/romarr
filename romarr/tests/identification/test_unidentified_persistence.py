"""Persistence integration test — Identifier flagged → unidentified_dump row.

Spec 001 FR-029: a file whose merged Identification confidence is
below 0.5 MUST be recorded in ``unidentified_dump`` with discovery
time, path, size, attempted hashes, attempt count, and last error.

This test ties together:
  - The :class:`Identifier` façade (returns an outcome with
    ``merged.is_unidentified``)
  - The :class:`Hasher` (computes the hashes that go on the row)
  - The persistent ``unidentified_dump`` table (FR-029 requirement)

A real importer pipeline (spec 008) does the persistence; spec 001's
foundation just needs to demonstrate the round-trip works.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Platform, UnidentifiedDump
from romarr.identification.hashmatch.cascade import HashMatchCascade
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
)
from romarr.identification.identifier import Identifier
from romarr.identification.parsers import default_dispatcher


class _EmptyBackend:
    name = BackendName.LOCAL

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        return HashLookupResult(backend=self.name, entries=())


@pytest.mark.asyncio
async def test_low_confidence_routes_to_unidentified_dump_persistence(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """End-to-end: Identifier sees a garbage filename + no DAT match → persists."""
    # 1. Set up minimum prerequisites.
    p = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(p)
    await async_session.commit()
    await async_session.refresh(p)

    rom = tmp_path / "game_001.bin"
    rom.write_bytes(b"\x00" * 100)

    # 2. Run the Identifier.
    identifier = Identifier(
        cascade=HashMatchCascade([_EmptyBackend()]),
        parser_dispatcher=default_dispatcher(),
    )
    outcome = await identifier.identify(path=rom, platform_id=p.id)

    assert outcome.merged.is_unidentified
    assert outcome.hashes is not None  # the hasher always runs

    # 3. Persist the FR-029 row — what spec 008's importer will do.
    row = UnidentifiedDump(
        path=str(rom),
        size_bytes=outcome.hashes.size_bytes,
        discovered_at=datetime.now(UTC),
        crc32=outcome.hashes.crc32,
        md5=outcome.hashes.md5,
        sha1=outcome.hashes.sha1,
        attempt_count=1,
        last_attempt_at=datetime.now(UTC),
        last_error=None,
        suggested_platform_id=p.id,
    )
    async_session.add(row)
    await async_session.commit()
    await async_session.refresh(row)

    # 4. Verify the row round-trips correctly.
    loaded = (
        await async_session.execute(select(UnidentifiedDump).where(UnidentifiedDump.id == row.id))
    ).scalar_one()
    assert loaded.path == str(rom)
    assert loaded.sha1 == outcome.hashes.sha1
    assert loaded.crc32 == outcome.hashes.crc32
    assert loaded.size_bytes == 100
    assert loaded.attempt_count == 1
    assert loaded.suggested_platform_id == p.id


@pytest.mark.asyncio
async def test_high_confidence_does_not_flag_as_unidentified(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Sanity check: a clean filename produces a non-unidentified outcome."""
    p = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(p)
    await async_session.commit()
    await async_session.refresh(p)

    rom = tmp_path / "Sonic the Hedgehog (USA).md"
    rom.write_bytes(b"\x00" * 100)

    identifier = Identifier(
        cascade=HashMatchCascade([_EmptyBackend()]),
        parser_dispatcher=default_dispatcher(),
    )
    outcome = await identifier.identify(path=rom, platform_id=p.id)

    assert not outcome.merged.is_unidentified
    assert outcome.merged.title == "Sonic the Hedgehog"


@pytest.mark.asyncio
async def test_unidentified_dump_path_is_globally_unique(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """FR-005-equivalent: each path appears at most once."""
    rom = tmp_path / "garbage.bin"
    rom.write_bytes(b"\x00" * 16)

    row1 = UnidentifiedDump(
        path=str(rom),
        size_bytes=16,
        discovered_at=datetime.now(UTC),
        attempt_count=0,
    )
    async_session.add(row1)
    await async_session.flush()

    row2 = UnidentifiedDump(
        path=str(rom),  # same path
        size_bytes=16,
        discovered_at=datetime.now(UTC),
        attempt_count=0,
    )
    async_session.add(row2)

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await async_session.flush()
    await async_session.rollback()
