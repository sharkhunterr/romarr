"""Sonarr-shape `/api/v3/system/status` endpoint (T053, FR-031, SC-001).

The endpoint is tiered by auth (per the spec 013 clarification):

  * **Public tier** (no principal): only ``{version, isProduction}``
    — sufficient for Sonarr-shape probe-recognition
    (Notifiarr / Recyclarr / Homepage). Minimises topology
    disclosure to unauthenticated scanners.
  * **Authenticated tier** (any role): the union of Sonarr v3 +
    Sonarr v4 fields — ``urlBase``, ``osName``, ``runtimeVersion``,
    ``appData``, ``startTime``, ``instanceName`` (v3 set) and
    ``databaseType``, ``databaseVersion``, ``migrationVersion``,
    ``runtimeName`` (v4 additions). JSON consumers tolerate
    unknown keys, so the union strictly broadens compat without
    breaking either era.

The endpoint is registered under ``/api/v3/system`` and is one of
the four intentionally public endpoints (FR-004).
"""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr import __version__
from romarr.api.dependencies import (
    get_current_principal,
    get_db,
    require_readonly,
)
from romarr.auth import Principal
from romarr.config import get_settings
from romarr.domain.models import Dump, Game, Release
from romarr.importer.models import ImportHistory

router = APIRouter(prefix="/api/v3/system", tags=["System"])

# The response schema is intentionally a free-form
# ``dict[str, Any]`` — Sonarr's actual response is loose JSON
# and the v3 → v4 union is open-ended. Pinning a Pydantic schema
# would make adding a v4.5 field a breaking change for the
# OpenAPI consumers.


def _database_type(database_url: str) -> str:
    """Derive Sonarr-style ``databaseType`` from a SQLAlchemy URL.

    Romarr ships with SQLite by default; PostgreSQL is the
    documented production alternative."""
    lowered = database_url.lower()
    if lowered.startswith(("postgresql", "postgres")):
        return "postgreSQL"
    return "sqLite"


@router.get("/status", response_model=None)
async def get_status(
    request: Request,
    principal: Annotated[
        Principal | None, Depends(get_current_principal)
    ],
) -> dict[str, Any]:
    """Sonarr-compatible system status.

    Public callers receive ``{version, isProduction}`` only;
    authenticated callers receive the full Sonarr v3 + v4 union
    field set (FR-031, SC-001)."""
    if principal is None:
        return {
            "version": __version__,
            "isProduction": True,
        }

    settings = get_settings()
    start_time = getattr(request.app.state, "_start_time", None)
    if start_time is None:
        # Defensive: the factory should have stamped this; if it
        # didn't (e.g. tests that mutate app.state), use now() as
        # the lower-bound — Sonarr clients only care that it's a
        # parseable ISO-8601 datetime.
        start_time = datetime.now(UTC)

    return {
        # Sonarr v3 baseline.
        "version": __version__,
        "isProduction": True,
        "instanceName": "Romarr",
        "urlBase": "",
        "osName": platform.system().lower(),
        "runtimeVersion": sys.version.split()[0],
        "appData": settings.data_dir,
        "startTime": start_time.isoformat().replace("+00:00", "Z"),
        # Sonarr v4 additions (per the spec 013 clarification on
        # the v3 vs v4 field set — emit the UNION).
        "databaseType": _database_type(settings.database_url),
        "databaseVersion": "",
        "migrationVersion": "",
        "runtimeName": "python",
    }


class SystemStats(BaseModel):
    """Aggregate counts surfaced on the Dashboard (slice 104).

    Cheap to compute (one COUNT per metric) so the Dashboard
    can poll it as often as it likes. The ``imports24h`` /
    ``importsSuccess24h`` pair lets the UI render a one-line
    "n imported today (m successful)" stat without a separate
    history scan.
    """

    model_config = ConfigDict(populate_by_name=True)

    total_games: int = Field(alias="totalGames")
    total_releases: int = Field(alias="totalReleases")
    total_dumps: int = Field(alias="totalDumps")
    monitored_games: int = Field(alias="monitoredGames")
    wanted_releases: int = Field(alias="wantedReleases")
    imports_24h: int = Field(alias="imports24h")
    imports_success_24h: int = Field(alias="importsSuccess24h")


@router.get(
    "/stats",
    response_model=SystemStats,
    response_model_by_alias=True,
    summary=(
        "Aggregate counts (games / releases / dumps / wanted / "
        "imports today). Drives the Dashboard stat cards."
    ),
)
async def get_stats(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemStats:
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    async def _scalar(stmt: Any) -> int:
        return int((await db.execute(stmt)).scalar_one() or 0)

    total_games = await _scalar(select(func.count()).select_from(Game))
    total_releases = await _scalar(
        select(func.count()).select_from(Release)
    )
    total_dumps = await _scalar(select(func.count()).select_from(Dump))
    monitored_games = await _scalar(
        select(func.count())
        .select_from(Game)
        .where(Game.monitored.is_(True))
    )
    wanted_releases = await _scalar(
        select(func.count())
        .select_from(Release)
        .where(
            Release.status == "wanted",
            Release.monitored.is_(True),
        )
    )
    imports_24h = await _scalar(
        select(func.count())
        .select_from(ImportHistory)
        .where(ImportHistory.started_at >= cutoff)
    )
    imports_success_24h = await _scalar(
        select(func.count())
        .select_from(ImportHistory)
        .where(
            ImportHistory.started_at >= cutoff,
            ImportHistory.success.is_(True),
        )
    )

    return SystemStats(
        totalGames=total_games,
        totalReleases=total_releases,
        totalDumps=total_dumps,
        monitoredGames=monitored_games,
        wantedReleases=wanted_releases,
        imports24h=imports_24h,
        importsSuccess24h=imports_success_24h,
    )


__all__ = ["router"]
