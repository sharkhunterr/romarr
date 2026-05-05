"""Tests for the DatUpdateRunner (spec 012 T051 + T047)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import DatEntry, Platform
from romarr.tasks.runners.dat_update import (
    DatSourceSpec,
    run_dat_update,
)

# Two platform fixtures sharing one DAT body so tests verify
# per-platform_id ingestion + per-source error handling.
_LOGIQX_MD = b"""<?xml version="1.0"?>
<datafile>
  <header>
    <name>Sega - Mega Drive</name>
    <version>20260501-001</version>
  </header>
  <game name="Sonic the Hedgehog (USA)">
    <rom name="Sonic the Hedgehog (USA).md"
         size="524288"
         crc="ABCD1234"
         sha1="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>
  </game>
</datafile>
"""

_LOGIQX_SNES = b"""<?xml version="1.0"?>
<datafile>
  <header>
    <name>Nintendo - SNES</name>
    <version>20260501-001</version>
  </header>
  <game name="Super Mario World (USA)">
    <rom name="Super Mario World (USA).sfc"
         size="524288"
         sha1="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"/>
  </game>
</datafile>
"""


@pytest.mark.asyncio
async def test_run_dat_update_downloads_and_ingests(
    async_session: AsyncSession,
) -> None:
    """spec 012 T047 (test_downloads_and_ingests) — runner
    fetches each source, hands the bytes to ``DatManager.ingest``,
    and the rows land in the ``dat_entry`` table."""
    md = Platform(slug="md", name="MD")
    snes = Platform(slug="snes", name="SNES")
    async_session.add_all([md, snes])
    await async_session.commit()

    fetched: list[str] = []

    async def _fake_fetch(url: str) -> bytes:
        fetched.append(url)
        if "snes" in url:
            return _LOGIQX_SNES
        return _LOGIQX_MD

    sources = [
        DatSourceSpec(
            url="https://no-intro.local/megadrive.dat",
            source="no-intro",
            platform_id=md.id,
        ),
        DatSourceSpec(
            url="https://no-intro.local/snes.dat",
            source="no-intro",
            platform_id=snes.id,
        ),
    ]
    result = await run_dat_update(
        async_session, sources=sources, fetcher=_fake_fetch
    )

    assert result.total == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert len(fetched) == 2

    rows = (await async_session.execute(select(DatEntry))).scalars().all()
    titles = {row.name for row in rows}
    assert titles == {
        "Sonic the Hedgehog (USA)",
        "Super Mario World (USA)",
    }


@pytest.mark.asyncio
async def test_dat_update_adapter_emits_on_dat_update_event(
    async_session: AsyncSession,
) -> None:
    """Slice 277 / spec 012 T047 — when a JobContext carries an
    ``event_channel``, the DatUpdateAdapter publishes one
    ``OnDatUpdate`` per successfully ingested source."""
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.notifications.types import OnDatUpdatePayload
    from romarr.tasks.runners.adapters import DatUpdateAdapter
    from romarr.tasks.types import JobContext, TriggerKind

    md = Platform(slug="md", name="MD")
    async_session.add(md)
    await async_session.commit()
    md_id = md.id

    async def _fake_fetch(url: str) -> bytes:
        return _LOGIQX_MD

    captured: list[OnDatUpdatePayload] = []

    class _ChannelStub:
        async def publish(self, event):  # type: ignore[no-untyped-def]
            assert isinstance(event, OnDatUpdatePayload)
            captured.append(event)

    sm = async_sessionmaker(async_session.bind, expire_on_commit=False)
    context = JobContext(
        job_id="DatUpdate",
        job_run_id=1,
        started_at=datetime.now(UTC),
        triggered_by=TriggerKind.MANUAL,
        progress_callback=lambda _c, _t, _m: None,
        cancellation_event=asyncio.Event(),
        parameters={
            "sources": [
                {
                    "url": "https://example/md.dat",
                    "source": "no-intro",
                    "platform_id": md_id,
                },
            ],
            # The adapter doesn't take a fetcher param yet; the
            # default fetcher would 502. We work around by
            # monkey-patching the runner's _default_fetcher via
            # the test fixture below.
        },
        sessionmaker=sm,
        event_channel=_ChannelStub(),
    )

    # Monkey-patch the default fetcher so the adapter goes through
    # the real code path without a network call.
    import romarr.tasks.runners.dat_update as _du

    orig = _du._default_fetcher
    _du._default_fetcher = _fake_fetch  # type: ignore[assignment]
    try:
        adapter = DatUpdateAdapter()
        await adapter._run(context)
    finally:
        _du._default_fetcher = orig  # type: ignore[assignment]

    assert len(captured) == 1
    assert captured[0].source == "no-intro"
    assert captured[0].platform == str(md_id)


@pytest.mark.asyncio
async def test_run_dat_update_records_per_source_failure(
    async_session: AsyncSession,
) -> None:
    """A single dead source is counted in ``failed`` but doesn't
    abort the sweep — the next source still gets ingested."""
    md = Platform(slug="md", name="MD")
    async_session.add(md)
    await async_session.commit()

    async def _fetcher(url: str) -> bytes:
        if "broken" in url:
            raise RuntimeError("HTTP 503")
        return _LOGIQX_MD

    sources = [
        DatSourceSpec(
            url="https://broken.local/megadrive.dat",
            source="no-intro",
            platform_id=md.id,
        ),
        DatSourceSpec(
            url="https://ok.local/megadrive.dat",
            source="no-intro",
            platform_id=md.id,
        ),
    ]
    result = await run_dat_update(
        async_session, sources=sources, fetcher=_fetcher
    )

    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.outcomes[0].error is not None
    assert "HTTP 503" in result.outcomes[0].error
    assert result.outcomes[1].error is None
    assert result.outcomes[1].inserted == 1


@pytest.mark.asyncio
async def test_run_dat_update_idempotent_on_second_pass(
    async_session: AsyncSession,
) -> None:
    """Re-running the same DAT body skips the ingest (FR-019)
    via DatManager's contents_hash short-circuit."""
    md = Platform(slug="md", name="MD")
    async_session.add(md)
    await async_session.commit()

    async def _fetcher(url: str) -> bytes:
        return _LOGIQX_MD

    sources = [
        DatSourceSpec(
            url="https://stable.local/megadrive.dat",
            source="no-intro",
            platform_id=md.id,
        ),
    ]
    first = await run_dat_update(
        async_session, sources=sources, fetcher=_fetcher
    )
    assert first.outcomes[0].inserted == 1
    assert first.outcomes[0].skipped_idempotent is False

    second = await run_dat_update(
        async_session, sources=sources, fetcher=_fetcher
    )
    assert second.outcomes[0].inserted == 0
    assert second.outcomes[0].skipped_idempotent is True


@pytest.mark.asyncio
async def test_run_dat_update_empty_sources_returns_zero(
    async_session: AsyncSession,
) -> None:
    """Empty source list — clean zero-counts, no fetcher calls."""
    called = False

    async def _fetcher(url: str) -> bytes:
        nonlocal called
        called = True
        return b""

    result = await run_dat_update(
        async_session, sources=[], fetcher=_fetcher
    )
    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.outcomes == []
    assert called is False
