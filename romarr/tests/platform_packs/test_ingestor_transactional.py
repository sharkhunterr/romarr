"""Transactional rollback tests (T028, SC-006, FR-007, FR-024)."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Platform, PlatformPack
from romarr.platform_packs import IngestSource, ingest_pack
from romarr.platform_packs.models import PlatformPackApplicationLog


@pytest.mark.asyncio
async def test_failed_ingest_rolls_back_data_and_records_failed_audit(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    pack_yaml: Callable[[str], bytes],
) -> None:
    """When an ingest fails mid-flight, the DATA side rolls back
    completely (no platform / format / platform_pack rows persist)
    while the AUDIT side records a ``status='failed'`` row in a
    fresh session (FR-024)."""
    sm = async_sessionmaker_factory

    # Inject a failure inside the transaction by monkeypatching the
    # post-platform parsing-strategy step. By that time the platform +
    # platform_pack rows are flushed but not committed; the rollback
    # MUST drop them.
    from romarr.platform_packs import ingestor

    async def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated mid-ingest failure")

    with patch.object(ingestor, "_apply_parsing_strategies", side_effect=_boom):
        async with sm() as s:
            with pytest.raises(RuntimeError, match="simulated"):
                await ingest_pack(
                    s,
                    sessionmaker=sm,
                    content=pack_yaml("valid/two_platforms.yaml"),
                    source=IngestSource(pack_source="community", applied_by="alice"),
                )

    # Data side: no platforms, no platform_pack row, no successful
    # audit row.
    async with sm() as s:
        platforms = (await s.execute(select(Platform))).scalars().all()
        packs = (await s.execute(select(PlatformPack))).scalars().all()
        logs = (
            (await s.execute(select(PlatformPackApplicationLog)))
            .scalars()
            .all()
        )
    assert platforms == []
    assert packs == []

    # Audit side: exactly one ``failed`` row with the captured error.
    assert len(logs) == 1
    failed = logs[0]
    assert failed.status == "failed"
    assert failed.action == "failed"
    assert "simulated" in (failed.error_message or "")
