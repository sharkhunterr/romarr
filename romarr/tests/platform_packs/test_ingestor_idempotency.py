"""Idempotency + version-conflict tests (T022, T023)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Platform
from romarr.platform_packs import (
    IngestSource,
    PackVersionConflictError,
    ingest_pack,
)
from romarr.platform_packs.models import PlatformPackApplicationLog


def _community() -> IngestSource:
    return IngestSource(pack_source="community", applied_by="alice")


@pytest.mark.asyncio
async def test_unchanged_pack_re_apply_is_skipped(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """SC-002: re-applying the SAME (pack_version, contents_hash) is a
    no-op for the data side and writes one ``skipped`` audit row."""
    sm = async_sessionmaker_factory
    body = pack_yaml("valid/minimal.yaml")

    async with sm() as s:
        first = await ingest_pack(
            s, sessionmaker=sm, content=body, source=_community()
        )
    assert first.action == "applied"

    async with sm() as s:
        plat_first = (
            await s.execute(select(Platform).where(Platform.slug == "megadrive"))
        ).scalar_one()
        first_updated_at = plat_first.updated_at

    async with sm() as s:
        second = await ingest_pack(
            s, sessionmaker=sm, content=body, source=_community()
        )

    assert second.action == "skipped"

    async with sm() as s:
        plat_second = (
            await s.execute(select(Platform).where(Platform.slug == "megadrive"))
        ).scalar_one()
    # The DB row was not touched.
    assert plat_second.updated_at == first_updated_at

    # Two audit-log rows: one ``applied`` and one ``skipped``.
    async with sm() as s:
        logs = (
            (
                await s.execute(
                    select(PlatformPackApplicationLog).order_by(
                        PlatformPackApplicationLog.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [r.action for r in logs] == ["applied", "skipped"]
    assert all(r.status == "success" for r in logs)


@pytest.mark.asyncio
async def test_same_version_different_hash_is_a_conflict(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """FR-010: a pack reusing an existing version with different
    contents_hash is rejected immediately."""
    sm = async_sessionmaker_factory
    async with sm() as s:
        await ingest_pack(
            s,
            sessionmaker=sm,
            content=pack_yaml("valid/minimal.yaml"),
            source=_community(),
        )

    # Mutate the description (hash changes; pack_version stays).
    mutated = pack_yaml("valid/minimal.yaml").replace(
        b'description: "Minimal one-platform pack"',
        b'description: "Mutated description"',
    )

    async with sm() as s:
        with pytest.raises(PackVersionConflictError):
            await ingest_pack(
                s,
                sessionmaker=sm,
                content=mutated,
                source=_community(),
            )


@pytest.mark.asyncio
async def test_pack_version_downgrade_rejected(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """FR-013a: lexically-older pack_version on a slug that already
    has a newer version recorded is rejected."""
    sm = async_sessionmaker_factory

    # Apply 2026.05.001 first.
    newer_body = (
        b"pack_version: '2026.05.001'\n"
        b"schema_version: 1\n"
        b"platforms:\n"
        b"  - slug: megadrive\n    name: Sega Mega Drive\n"
        b"    manufacturer: Sega\n"
        b"    formats:\n"
        b"      - extension: '.md'\n        format_type: cartridge\n"
    )
    async with sm() as s:
        await ingest_pack(
            s, sessionmaker=sm, content=newer_body, source=_community()
        )

    # Now try a 2026.04.001 pack on the same slug — must reject.
    async with sm() as s:
        with pytest.raises(PackVersionConflictError):
            await ingest_pack(
                s,
                sessionmaker=sm,
                content=pack_yaml("valid/minimal.yaml"),
                source=_community(),
            )
