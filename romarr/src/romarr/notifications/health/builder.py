"""HealthEngine builder (spec 011 T057).

Constructs a fully-wired :class:`HealthEngine` from the live
configuration: one DAT-freshness check per (source, platform),
one library check per Library row (path + disk space), one
check per indexer, one per download client, one per enabled
metadata provider, plus the always-on DB and metadata-cache
size checks.

The lifespan calls :func:`build_health_engine` once on startup
when ``Settings.bootstrap_enabled`` is True, stashes the
result on ``app.state.health_engine``, and the scheduler's
``HealthCheckAdapter`` consumes it through the ``JobContext``
so a periodic refresh cron always probes a current snapshot.

Failure modes that DON'T paralyse the startup:
  - A row that fails to construct its check (decryption failed,
    library row carries a bad path, etc.) is logged and skipped.
  - Empty configuration → an engine with just the DB + cache
    checks. Refresh still runs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from romarr.domain.models import DatEntry
from romarr.indexers.models import Indexer
from romarr.libraries.models import Library
from romarr.metadata.health import MetadataCacheSizeHealthCheck
from romarr.metadata.models import MetadataProviderConfig
from romarr.notifications.health.checks.dat_freshness import (
    DatFreshnessHealthCheck,
)
from romarr.notifications.health.checks.db import DbHealthCheck
from romarr.notifications.health.checks.disk_space import (
    DiskSpaceHealthCheck,
)
from romarr.notifications.health.checks.download_client import (
    DownloadClientHealthCheck,
)
from romarr.notifications.health.checks.indexer import IndexerHealthCheck
from romarr.notifications.health.checks.library_path import (
    LibraryPathHealthCheck,
)
from romarr.notifications.health.checks.metadata_provider import (
    MetadataProviderHealthCheck,
)
from romarr.notifications.health.engine import HealthEngine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from romarr.notifications.health.checks.base import HealthCheck

_logger = logging.getLogger(__name__)


SessionFactory = Callable[[], Awaitable["AsyncSession"]]


async def build_health_engine(
    sessionmaker: "async_sessionmaker[AsyncSession]",
) -> HealthEngine:
    """Assemble the production HealthEngine.

    The session factory is closed-over so each cycle gets a
    fresh session (the engine's ``refresh()`` already creates
    one internally; per-check factories wrap in `async with`
    so a hung check can't leak its session).

    Returns an engine with at least the DB + cache-size checks;
    additional per-row checks land when the corresponding
    config rows exist.
    """
    checks: list[HealthCheck] = []

    async def _factory() -> "AsyncSession":
        return sessionmaker()

    # Always-on infrastructure checks.
    checks.append(
        DbHealthCheck(session_factory=_factory, component_id="db")
    )
    checks.append(
        MetadataCacheSizeHealthCheck(
            session_factory=_factory,
            component_id="metadata.cache",
        )
    )

    # Per-row checks read the current config inside one short-
    # lived session.
    async with sessionmaker() as session:
        await _add_library_checks(checks, session)
        await _add_dat_freshness_checks(checks, session)
        await _add_indexer_checks(checks, session, sessionmaker)
        await _add_download_client_checks(
            checks, session, sessionmaker
        )
        await _add_metadata_provider_checks(checks, session)

    _logger.info(
        "health.engine_built",
        extra={"check_count": len(checks)},
    )
    return HealthEngine(
        checks=checks,
        session_factory=_factory,
    )


async def _add_library_checks(
    checks: "list[HealthCheck]", session: "AsyncSession"
) -> None:
    rows = (await session.execute(select(Library))).scalars().all()
    for row in rows:
        try:
            path = Path(row.path)
        except Exception as exc:
            _logger.warning(
                "health.library_skipped_bad_path",
                extra={"library_id": row.id, "error": str(exc)},
            )
            continue
        checks.append(
            LibraryPathHealthCheck(
                component_id=f"library.path.{row.id}",
                path=path,
            )
        )
        checks.append(
            DiskSpaceHealthCheck(
                component_id=f"library.disk.{row.id}",
                path=path,
                min_free_gb=row.min_disk_free_gb,
            )
        )


async def _add_dat_freshness_checks(
    checks: "list[HealthCheck]", session: "AsyncSession"
) -> None:
    """One check per distinct (source, platform_id) pair —
    DAT entries carry the per-pack ``last_updated_at`` we need
    via the most recent row's ``updated_at`` timestamp."""
    rows = (
        await session.execute(
            select(DatEntry.source, DatEntry.platform_id, DatEntry.updated_at)
            .order_by(DatEntry.updated_at.desc())
        )
    ).all()
    seen: set[tuple[str, int]] = set()
    for source, platform_id, updated_at in rows:
        key = (source, platform_id)
        if key in seen:
            continue
        seen.add(key)
        checks.append(
            DatFreshnessHealthCheck(
                component_id=f"dat:{source}:platform-{platform_id}",
                last_updated_at=updated_at,
            )
        )


async def _add_indexer_checks(
    checks: "list[HealthCheck]",
    session: "AsyncSession",
    sessionmaker: "async_sessionmaker[AsyncSession]",
) -> None:
    # Every configured indexer gets a health check — there's no
    # dedicated "enabled" toggle on Indexer (the spec splits the
    # flag into enable_rss / enable_automatic_search /
    # enable_interactive_search). An operator who wired the
    # row wants reachability surfaced regardless.
    rows = (
        await session.execute(select(Indexer))
    ).scalars().all()
    for row in rows:
        # Snapshot the row's id so the closure doesn't capture
        # the SQLAlchemy instance (which becomes detached after
        # the outer session exits).
        indexer_id = row.id
        checks.append(
            IndexerHealthCheck(
                indexer_id=indexer_id,
                client_factory=_make_indexer_client_factory(
                    sessionmaker, indexer_id
                ),
                component_id=f"indexer.{indexer_id}",
            )
        )


def _make_indexer_client_factory(
    sessionmaker: "async_sessionmaker[AsyncSession]",
    indexer_id: int,
) -> Callable[[], Awaitable[Any]]:
    """Closure that builds a fresh ``NewznabClient`` per probe."""

    async def _factory() -> Any:
        from romarr.search._clients import make_indexer_client_factory

        async with sessionmaker() as session:
            inner = make_indexer_client_factory(session)
            return await inner(indexer_id)

    return _factory


async def _add_download_client_checks(
    checks: "list[HealthCheck]",
    session: "AsyncSession",
    sessionmaker: "async_sessionmaker[AsyncSession]",
) -> None:
    from romarr.downloaders.models import DownloadClient as DownloadClientRow

    rows = (
        await session.execute(
            select(DownloadClientRow).where(
                DownloadClientRow.enabled.is_(True)
            )
        )
    ).scalars().all()
    for row in rows:
        client_id = row.id
        checks.append(
            DownloadClientHealthCheck(
                client_id=client_id,
                client_factory=_make_download_client_factory(
                    sessionmaker, client_id
                ),
                component_id=f"downloadclient.{client_id}",
            )
        )


def _make_download_client_factory(
    sessionmaker: "async_sessionmaker[AsyncSession]",
    client_id: int,
) -> Callable[[], Awaitable[Any]]:
    async def _factory() -> Any:
        from romarr.search._clients import (
            make_download_client_factory,
        )

        async with sessionmaker() as session:
            inner = make_download_client_factory(session)
            return await inner(client_id)

    return _factory


async def _add_metadata_provider_checks(
    checks: "list[HealthCheck]", session: "AsyncSession"
) -> None:
    rows = (
        await session.execute(
            select(MetadataProviderConfig).where(
                MetadataProviderConfig.enabled.is_(True)
            )
        )
    ).scalars().all()
    if not rows:
        return
    try:
        from romarr.metadata.registry import load_enabled_providers

        providers = await load_enabled_providers(session, scan=False)
    except Exception as exc:
        _logger.warning(
            "health.providers_skipped",
            extra={"error": str(exc)},
        )
        return
    for provider in providers:
        checks.append(
            MetadataProviderHealthCheck(
                provider=provider,
                component_id=f"metadata.{provider.name}",
            )
        )


__all__ = ["build_health_engine"]
