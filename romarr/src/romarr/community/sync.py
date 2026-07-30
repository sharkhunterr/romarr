"""Sync engine — the per-source check + apply orchestration.

The engine is stateless; it takes a session + a source row, calls
the adapter, updates the row's tracking columns, commits. Callers:

  * the scheduled task ``community_sync`` (all ``enabled`` +
    ``auto_check`` sources at once);
  * the manual "Vérifier maintenant" / "Appliquer" endpoints
    (one source, force-fetch).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.community.adapters import get_adapter
from romarr.community.schemas import ApplyResult, CheckResult
from romarr.platform_packs.models import PackSource

_LOG = logging.getLogger(__name__)


async def check_source(
    source: PackSource, session: AsyncSession
) -> CheckResult:
    """Fetch the manifest, update ``last_seen_version`` + timestamps,
    commit. Never mutates the target subsystem.
    """
    adapter = get_adapter(source.resource_type)
    if adapter is None:
        result = CheckResult(
            error=f"no adapter registered for resource_type={source.resource_type!r}"
        )
    else:
        result = await adapter.check(source)

    source.last_synced_at = datetime.now(UTC)
    if result.error:
        source.last_status = "error"
        source.last_error = result.error
    else:
        source.last_status = "ok"
        source.last_error = None
        if result.available_version:
            source.last_seen_version = result.available_version
    await session.commit()
    return result


async def apply_source(
    source: PackSource, session: AsyncSession
) -> ApplyResult:
    """Fetch + validate + ingest via the adapter, update
    ``installed_version`` + apply counters on success.

    Refuses to run when ``source.trust_status == "pending"``. The
    caller (endpoint / UI) is responsible for flipping trust to
    ``trusted`` after showing the manifest preview.
    """
    if source.trust_status == "pending":
        return ApplyResult(
            applied_version=source.installed_version or "",
            applied_count=0,
            error="source pending — preview + accept before apply",
        )

    adapter = get_adapter(source.resource_type)
    if adapter is None:
        return ApplyResult(
            applied_version=source.installed_version or "",
            applied_count=0,
            error=f"no adapter for resource_type={source.resource_type!r}",
        )

    result = await adapter.apply(source, session)

    source.last_synced_at = datetime.now(UTC)
    source.last_applied_count = result.applied_count
    if result.error:
        source.last_status = "error"
        source.last_error = result.error
    else:
        source.last_status = "partial" if result.warnings else "ok"
        source.last_error = "; ".join(result.warnings) if result.warnings else None
        if result.applied_version:
            source.installed_version = result.applied_version
            # An apply is authoritative — mirror on last_seen so
            # the "update available" indicator clears.
            source.last_seen_version = result.applied_version
    await session.commit()
    return result


async def sweep_all(session: AsyncSession) -> dict[int, CheckResult]:
    """Iterate every ``enabled AND auto_check`` source and run
    :func:`check_source`. Returns per-source-id CheckResult.

    Called by the scheduled task runner. Does NOT apply — check only.
    """
    rows = (
        (
            await session.execute(
                select(PackSource).where(
                    PackSource.enabled.is_(True),
                    PackSource.auto_check.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    results: dict[int, CheckResult] = {}
    for source in rows:
        try:
            results[source.id] = await check_source(source, session)
        except Exception as exc:  # noqa: BLE001 — swallow per-source, keep sweeping
            _LOG.warning(
                "community sync failed for source id=%s url=%s: %s",
                source.id,
                source.url,
                exc,
            )
            source.last_status = "error"
            source.last_error = f"unexpected: {exc}"
            source.last_synced_at = datetime.now(UTC)
            await session.commit()
            results[source.id] = CheckResult(error=str(exc))
    return results


__all__ = ["apply_source", "check_source", "sweep_all"]
