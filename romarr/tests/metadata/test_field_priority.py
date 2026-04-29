"""field_priority schema constraints (T010)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.metadata.models import FieldPriority


async def test_unique_rank_per_field(async_session: AsyncSession) -> None:
    """Two providers cannot share priority_order=1 within the same field."""
    async_session.add(
        FieldPriority(
            field_name="title",
            provider_name="igdb",
            priority_order=1,
            updated_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    async_session.add(
        FieldPriority(
            field_name="title",
            provider_name="screenscraper",
            priority_order=1,  # collision on (title, 1)
            updated_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_same_provider_can_appear_for_different_fields(
    async_session: AsyncSession,
) -> None:
    """The composite PK is (field_name, provider_name) — the same
    provider may rank in many fields without conflicting."""
    async_session.add_all(
        [
            FieldPriority(
                field_name="title",
                provider_name="igdb",
                priority_order=1,
                updated_at=datetime.now(UTC),
            ),
            FieldPriority(
                field_name="summary",
                provider_name="igdb",
                priority_order=1,
                updated_at=datetime.now(UTC),
            ),
        ]
    )
    await async_session.commit()
    # No exception → constraints honored.
