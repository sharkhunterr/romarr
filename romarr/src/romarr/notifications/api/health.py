"""Health endpoints (FR-024a, FR-024b).

  - GET  /api/v3/health           — tiered response. Anonymous
    callers get only ``{status: "ok"|"warning"|"error"}``;
    authenticated callers (any role; ``read`` scope sufficient)
    get the full per-component breakdown with messages.
  - POST /api/v3/health/refresh   — admin-only; runs the
    engine cycle on demand (operator clicked "refresh now").

The unauthenticated response is intentionally minimal: a public
status badge for dashboards / status pages, no internal error
detail. The full breakdown leaks indexer host names and
download-client types — admin-internal at minimum.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import (
    get_current_principal,
    get_db,
    require_admin,
)
from romarr.auth import Principal
from romarr.notifications.health.snapshot import build_snapshot
from romarr.notifications.models import HealthCheck as HealthCheckRow
from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

router = APIRouter(prefix="/api/v3/health", tags=["Health"])


@router.get("")
async def get_health(
    session: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[
        Principal | None, Depends(get_current_principal)
    ],
) -> dict[str, Any]:
    """Tiered health snapshot.

    Anonymous: ``{status: "ok"|"warning"|"error"}`` only.
    Authenticated (any role): full ``HealthSnapshot`` with
    per-category breakdown and structured messages.
    """
    snapshot = await _load_snapshot(session)
    if principal is None:
        return {"status": snapshot.overall_status.value}
    return _serialize_full(snapshot)


@router.post("/refresh")
async def refresh_health(
    _admin: Annotated[Principal, Depends(require_admin)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Run the engine on demand. Admin-gated because each cycle
    fires outbound HTTP probes against indexers / download
    clients (SSRF surface, FR-024b).

    The engine instance is read off ``request.app.state``; if
    the lifespan hasn't installed one yet, returns the
    persisted snapshot without refreshing (so the endpoint is
    still callable for a UI ping).
    """
    engine = getattr(request.app.state, "health_engine", None)
    if engine is None:
        snapshot = await _load_snapshot(session)
        return _serialize_full(snapshot)
    fresh_snapshot = await engine.refresh()
    return _serialize_full(fresh_snapshot)


# ---------------------------------------------------------------------------
# Internals


async def _load_snapshot(session: AsyncSession) -> Any:
    """Read the persisted ``health_check`` rows and aggregate.

    Returns the same :class:`HealthSnapshot` shape the engine
    produces, so the serializer doesn't care whether the data
    came from a fresh cycle or the persisted state.
    """
    rows = (
        await session.execute(select(HealthCheckRow))
    ).scalars().all()
    results = [
        HealthCheckResult(
            component=row.component,
            category=ComponentCategory(_safe_category(row.component)),
            status=HealthStatus(row.status),
            message=row.message,
        )
        for row in rows
    ]
    return build_snapshot(results=results, refreshed_at=datetime.now(UTC))


def _safe_category(component: str) -> str:
    """Derive the :class:`ComponentCategory` from the component
    id's namespace prefix (``indexer:X`` → ``indexer``,
    ``library:Cartridges`` → ``library``, ``db`` → ``db``).
    Falls back to ``db`` if the prefix isn't recognised so the
    snapshot doesn't crash on legacy rows."""
    prefix = component.split(":", 1)[0] if ":" in component else component
    valid = {c.value for c in ComponentCategory}
    if prefix in valid:
        return prefix
    return ComponentCategory.DB.value


def _serialize_full(snapshot: Any) -> dict[str, Any]:
    return {
        "status": snapshot.overall_status.value,
        "refreshed_at": snapshot.refreshed_at.isoformat(),
        "by_category": {
            category.value: [
                {
                    "component": result.component,
                    "status": result.status.value,
                    "message": result.message,
                }
                for result in results
            ]
            for category, results in snapshot.by_category.items()
        },
    }


__all__ = ["router"]
