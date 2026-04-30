"""Health-issue persistence tests (T067)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers import (
    IndexerHealthIssue,
    clear_health,
    record_health_issue,
)
from romarr.indexers.models import Indexer


async def _seed_indexer(session: AsyncSession) -> Indexer:
    row = Indexer(
        name="Health Test",
        implementation="newznab",
        url="https://health.test/api",
        source="manual",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_record_health_issue_writes_columns(
    async_session: AsyncSession,
) -> None:
    """T067: record_health_issue stamps the indexer row's health
    columns with the issue's category + message."""
    indexer = await _seed_indexer(async_session)
    occurred = datetime.now(UTC)

    await record_health_issue(
        async_session,
        IndexerHealthIssue(
            indexer_id=indexer.id,
            indexer_name=indexer.name,
            category="auth",
            message="HTTP 401",
            occurred_at=occurred,
        ),
    )

    row = (
        await async_session.execute(
            select(Indexer).where(Indexer.id == indexer.id)
        )
    ).scalar_one()
    assert row.last_health_ok is False
    assert "auth: HTTP 401" in (row.last_health_error or "")
    assert row.last_health_at is not None


@pytest.mark.asyncio
async def test_record_health_issue_unknown_indexer_is_no_op(
    async_session: AsyncSession,
) -> None:
    """An issue for a missing indexer logs but doesn't raise."""
    await record_health_issue(
        async_session,
        IndexerHealthIssue(
            indexer_id=9_999,
            indexer_name="ghost",
            category="protocol",
            message="unreachable",
            occurred_at=datetime.now(UTC),
        ),
    )


@pytest.mark.asyncio
async def test_clear_health_resets_columns(
    async_session: AsyncSession,
) -> None:
    indexer = await _seed_indexer(async_session)
    # Stamp the row with a failure first.
    await record_health_issue(
        async_session,
        IndexerHealthIssue(
            indexer_id=indexer.id,
            indexer_name=indexer.name,
            category="auth",
            message="HTTP 401",
            occurred_at=datetime.now(UTC),
        ),
    )
    # Now clear it.
    await clear_health(async_session, indexer_id=indexer.id)

    row = (
        await async_session.execute(
            select(Indexer).where(Indexer.id == indexer.id)
        )
    ).scalar_one()
    assert row.last_health_ok is True
    assert row.last_health_error is None
