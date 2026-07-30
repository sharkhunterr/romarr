"""CommunitySync — periodic *check* of every registered community source.

**Check-only**, not apply. The unified Update Center refreshes each
enabled + auto_check source's ``last_seen_version`` on the sweep so
the header badge lights up amber when a manifest advertises a new
version. Applying stays operator-driven (per the "no silent apply"
ADR from the design discussion).

Complements the legacy :mod:`~romarr.tasks.runners.pack_sources_sync`
runner, which does full YAML re-apply for ``resource_type='platform_pack'``
rows only. This sweep runs across every ``resource_type`` and
delegates to the registered adapter via :func:`romarr.community.sync.sweep_all`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import romarr.community  # noqa: F401 — registers adapters
from romarr.community.sync import sweep_all

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_logger = logging.getLogger(__name__)


@dataclass
class CommunitySyncResult:
    total_sources: int = 0
    updates_available: int = 0
    errors: int = 0
    per_source: dict[int, str | None] = field(default_factory=dict)
    """Per-source-id → error message ("" for success)."""


async def run_community_sync(
    session: "AsyncSession",
    *,
    sessionmaker: "async_sessionmaker[AsyncSession]",
) -> CommunitySyncResult:
    """Check-only sweep of every enabled + auto_check source.

    ``sessionmaker`` is accepted for parity with other runners but
    unused today (sweep_all reuses the outer session for row
    updates; the adapters run against the same session).
    """
    per_source_results = await sweep_all(session)

    result = CommunitySyncResult(total_sources=len(per_source_results))
    for source_id, check_result in per_source_results.items():
        if check_result.error:
            result.errors += 1
            result.per_source[source_id] = check_result.error[:512]
            continue
        result.per_source[source_id] = None

    # Count how many sources now advertise a version newer than
    # what's installed — piggy-back on the sync engine's own
    # last_seen_version write to avoid re-computing here.
    # (We don't have the row objects handy; the badge feed
    # (GET /api/v3/community/updates) does the compare each time
    # it's called, cheaper than another DB roundtrip here.)

    _logger.info(
        "tasks.community_sync.complete",
        extra={
            "sources": result.total_sources,
            "errors": result.errors,
        },
    )
    return result


__all__ = ["CommunitySyncResult", "run_community_sync"]
