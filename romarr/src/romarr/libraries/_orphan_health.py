"""Orphan-releases startup health check (spec 009 CL003 / FR-003a).

After the spec 009 migration runs the path-prefix backfill, a
Release row may still have ``library_id IS NULL`` if its Dump
path doesn't match any Library's canonical path (e.g., the
Library was renamed mid-migration, or the Dump was rehomed
manually). When that happens, the Wanted page lies — the
Release belongs to no library and never gets scanned.

This module ships the runtime check the migration can't do
itself (migrations don't have access to the EventChannel).
:func:`check_orphan_releases_on_startup` runs once during
lifespan startup, counts orphans, and emits a single
``OnHealthIssue`` event with the count when > 0. The check is
idempotent — re-running fires the same event again, which the
notification dispatcher dedups by category.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from romarr.domain.models import Release
from romarr.notifications.types import (
    ComponentCategory,
    EventType,
    HealthStatus,
    OnHealthIssuePayload,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.notifications.channel import EventChannel

logger = logging.getLogger(__name__)


_HEALTH_CATEGORY = "orphan-releases"


async def check_orphan_releases_on_startup(
    *,
    sessionmaker: "async_sessionmaker",
    event_channel: "EventChannel",
) -> int:
    """Count orphan Releases + emit ``OnHealthIssue`` when > 0.

    Returns the number of orphan Releases found (zero when
    healthy). Failures are swallowed — health-check failure
    must not paralyse startup.
    """
    try:
        async with sessionmaker() as session:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(Release)
                    .where(Release.library_id.is_(None))
                )
            ).scalar_one()
    except Exception:
        logger.exception("orphan_releases_check.query_failed")
        return 0

    if count > 0:
        try:
            await event_channel.publish(
                OnHealthIssuePayload(
                    component=_HEALTH_CATEGORY,
                    category=ComponentCategory.LIBRARY,
                    severity="warning",
                    previous_status=HealthStatus.OK,
                    current_status=HealthStatus.WARNING,
                    message=(
                        f"{count} Release(s) have no library_id — they "
                        "won't be scanned. Re-run the library backfill "
                        "or attach them via the manual-import endpoint."
                    ),
                )
            )
        except Exception:
            logger.exception("orphan_releases_check.publish_failed")

    return int(count)


__all__ = ["check_orphan_releases_on_startup"]
