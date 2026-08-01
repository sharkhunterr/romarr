"""First-boot bootstrap of preseeded community sources.

Migration 0042 registers a "Romarr Official Platforms" source in
``pack_sources`` and disables the wheel-bundled builtin auto-apply.
This module's :func:`bootstrap_official_sources` is called from the
FastAPI lifespan hook as an ``asyncio.create_task`` so the server
starts serving immediately while the manifest fetch runs in the
background.

Contract :

  * Runs one full check + apply cycle per ``trusted`` source that
    has ``installed_version IS NULL`` (never applied) OR
    ``auto_check=True`` AND a newer ``last_seen_version`` than what's
    installed. In practice: fresh installs get the pack; upgrades
    re-apply when the community bumped the manifest version.
  * Failures per-source are logged and don't block the sweep — a
    dead mirror leaves the DB empty and surfaces via the empty-state
    UI banner, without breaking the app.
  * The whole coroutine is fire-and-forget from the lifespan's
    perspective; nothing awaits its completion.
"""

from __future__ import annotations

import logging

import romarr.community  # noqa: F401 — registers adapters
from romarr.community.sync import apply_source, check_source
from romarr.community.versioning import is_newer
from romarr.platform_packs.models import PackSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

_LOG = logging.getLogger(__name__)


async def _bootstrap_one(session: AsyncSession, source: PackSource) -> None:
    """Check the source; apply if it's new or an update landed."""
    check_result = await check_source(source, session)
    if check_result.error:
        _LOG.warning(
            "community.bootstrap.check_failed",
            extra={
                "source_id": source.id,
                "source_name": source.name,
                "error": check_result.error,
            },
        )
        return

    needs_apply = source.installed_version is None or is_newer(
        source.last_seen_version, source.installed_version
    )
    if not needs_apply:
        _LOG.info(
            "community.bootstrap.up_to_date",
            extra={
                "source_id": source.id,
                "source_name": source.name,
                "installed_version": source.installed_version,
            },
        )
        return

    apply_result = await apply_source(source, session)
    _LOG.info(
        "community.bootstrap.applied",
        extra={
            "source_id": source.id,
            "source_name": source.name,
            "applied_version": apply_result.applied_version,
            "applied_count": apply_result.applied_count,
            "error": apply_result.error,
            "warnings_count": len(apply_result.warnings),
        },
    )


async def bootstrap_official_sources(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Sweep every trusted+enabled+auto_check preseeded source.

    Called from the lifespan hook as a background task. Never
    raises — every failure is logged and the sweep continues.
    """
    try:
        async with sessionmaker() as session:
            rows = (
                (
                    await session.execute(
                        select(PackSource).where(
                            PackSource.enabled.is_(True),
                            PackSource.auto_check.is_(True),
                            PackSource.trust_status == "trusted",
                        )
                    )
                )
                .scalars()
                .all()
            )
            for source in rows:
                try:
                    await _bootstrap_one(session, source)
                except Exception as exc:  # noqa: BLE001 — swallow, keep sweeping
                    _LOG.warning(
                        "community.bootstrap.source_failed",
                        exc_info=True,
                        extra={
                            "source_id": source.id,
                            "source_name": source.name,
                            "error": str(exc),
                        },
                    )
    except Exception:  # noqa: BLE001 — never break the lifespan
        _LOG.warning("community.bootstrap.sweep_failed", exc_info=True)


__all__ = ["bootstrap_official_sources"]
