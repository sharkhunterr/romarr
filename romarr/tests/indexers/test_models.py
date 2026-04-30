"""Indexer + Application model round-trip tests (T006-T008)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Application, Indexer


async def test_indexer_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        Indexer(
            name="My Indexer",
            implementation="newznab",
            url="https://example.test/api",
            categories=[1060, 7010],
            source="manual",
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(Indexer).where(Indexer.name == "My Indexer")
        )
    ).scalar_one()
    assert row.implementation == "newznab"
    assert row.categories == [1060, 7010]
    assert row.source == "manual"
    assert row.priority == 25  # default
    assert row.timeout_seconds == 30  # default
    assert row.result_limit == 100  # default


async def test_unique_url_per_impl(async_session: AsyncSession) -> None:
    """Inserting the same (implementation, url) twice violates UNIQUE."""
    async_session.add(
        Indexer(
            name="A",
            implementation="newznab",
            url="https://dup.example/api",
            source="manual",
        )
    )
    await async_session.commit()

    async_session.add(
        Indexer(
            name="B",
            implementation="newznab",
            url="https://dup.example/api",  # collision
            source="manual",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_application_unique_prowlarr_url(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        Application(
            name="Prowlarr A",
            sync_level="full_sync",
            prowlarr_url="https://prowlarr.test",
            prowlarr_api_key_encrypted=b"ciphertext-1",
            app_token_hash="hash-1",
            created_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    async_session.add(
        Application(
            name="Prowlarr B",
            sync_level="full_sync",
            prowlarr_url="https://prowlarr.test",  # collision
            prowlarr_api_key_encrypted=b"ciphertext-2",
            app_token_hash="hash-2",
            created_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_indexer_implementation_check_constraint(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        Indexer(
            name="Bad",
            implementation="not-a-real-impl",
            url="https://bad.test/api",
            source="manual",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_indexer_priority_range_check(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        Indexer(
            name="Out of range",
            implementation="newznab",
            url="https://oor.test/api",
            source="manual",
            priority=999,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()
