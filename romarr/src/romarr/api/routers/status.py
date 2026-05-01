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
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from romarr import __version__
from romarr.api.dependencies import get_current_principal
from romarr.auth import Principal
from romarr.config import get_settings

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


__all__ = ["router"]
