"""Tests for the CutoffSearch + MissingSearch adapters wired
to the spec 007 rounds (slice 203 / spec 012 T021 closure)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Game, Platform, Release
from romarr.tasks.runners.adapters import (
    CutoffSearchAdapter,
    MissingSearchAdapter,
)


def _fake_context(
    *,
    job_id: str,
    sessionmaker: async_sessionmaker[AsyncSession] | None,
    parameters: dict[str, object] | None = None,
) -> SimpleNamespace:
    """Duck-typed ``JobContext`` substitute. The frozen Pydantic
    model can't have a ``sessionmaker`` attached after the fact,
    so the adapter contract uses ``getattr(context, ...)`` —
    SimpleNamespace satisfies it without the model overhead."""
    return SimpleNamespace(
        job_id=job_id,
        job_run_id=1,
        triggered_by=SimpleNamespace(value="cron"),
        sessionmaker=sessionmaker,
        parameters=parameters or {},
    )


async def _seed_release(
    sm: async_sessionmaker[AsyncSession],
    *,
    title: str,
    status: str = "wanted",
    cutoff_met: bool = False,
) -> None:
    async with sm() as session:
        platform = Platform(slug=f"p-{title.lower()}", name=title)
        session.add(platform)
        await session.flush()
        game = Game(platform_id=platform.id, slug=title.lower(), title=title)
        session.add(game)
        await session.flush()
        session.add(
            Release(
                game_id=game.id,
                name=f"{title} (USA)",
                status=status,
                monitored=True,
                cutoff_met=cutoff_met,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_missing_search_adapter_falls_back_without_sessionmaker() -> None:
    """No sessionmaker → adapter returns the documented stub.
    Catches the regression where a refactor accidentally
    crashes the scheduler dispatch on a misconfigured app."""
    adapter = MissingSearchAdapter()
    context = _fake_context(
        job_id="MissingSearch", sessionmaker=None
    )
    result = await adapter._run(context)
    assert result.summary["stub"] is True
    assert result.summary["reason"] == "no sessionmaker"


@pytest.mark.asyncio
async def test_cutoff_search_adapter_falls_back_without_sessionmaker() -> None:
    adapter = CutoffSearchAdapter()
    context = _fake_context(
        job_id="CutoffSearch", sessionmaker=None
    )
    result = await adapter._run(context)
    assert result.summary["stub"] is True


@pytest.mark.asyncio
async def test_missing_search_adapter_invokes_real_round(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """With a sessionmaker + an empty parameters dict, the
    adapter calls into ``run_missing_search`` and returns its
    aggregated counts."""
    sm = async_sessionmaker_factory
    await _seed_release(sm, title="Sonic", status="wanted")
    await _seed_release(sm, title="Mario", status="wanted")
    # An imported one shouldn't get probed by missing-search.
    await _seed_release(sm, title="Zelda", status="imported")

    adapter = MissingSearchAdapter()
    context = _fake_context(
        job_id="MissingSearch", sessionmaker=sm
    )
    result = await adapter._run(context)
    # Two wanted Releases → two probes. The default search_fn
    # would hit live indexers; the runner short-circuits when
    # no indexers are configured (empty result), so total=2 +
    # succeeded=2 + grabbed=0 is the expected shape.
    assert result.summary["total"] == 2


@pytest.mark.asyncio
async def test_cutoff_search_adapter_invokes_real_round(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    sm = async_sessionmaker_factory
    await _seed_release(
        sm, title="Sonic", status="imported", cutoff_met=False
    )
    await _seed_release(
        sm, title="Mario", status="imported", cutoff_met=True
    )
    await _seed_release(
        sm, title="Zelda", status="wanted"
    )

    adapter = CutoffSearchAdapter()
    context = _fake_context(
        job_id="CutoffSearch", sessionmaker=sm
    )
    result = await adapter._run(context)
    # One imported + below-cutoff + monitored Release.
    assert result.summary["total"] == 1


@pytest.mark.asyncio
async def test_missing_search_adapter_honours_limit_parameter(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Operator-supplied ``parameters['limit']`` flows through
    to ``run_missing_search``."""
    sm = async_sessionmaker_factory
    for title in ("A", "B", "C", "D", "E"):
        await _seed_release(sm, title=title, status="wanted")

    adapter = MissingSearchAdapter()
    context = _fake_context(
        job_id="MissingSearch",
        sessionmaker=sm,
        parameters={"limit": 2},
    )
    result = await adapter._run(context)
    assert result.summary["total"] == 2
