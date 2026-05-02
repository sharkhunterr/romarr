"""WebSocket on-upgrade auth resolver (T070, FR-018).

Reuses spec 010's auth chain (:func:`romarr.auth.resolve_principal`)
so the WS surface accepts the same auth methods as HTTP:

  * X-Api-Key header on the upgrade
  * ?apikey=... query parameter
  * Cookie session (after a prior /api/v3/auth/login)
  * Bearer JWT (Authorization header)
  * Reverse-proxy headers (when ChainConfig.trust_proxy_headers)

If nothing matches, the upgrade is rejected with WebSocket
close code 1008 (policy violation), mirroring the HTTP 401
contract for the equivalent REST surface (FR-018).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from romarr.auth import (
    ChainConfig,
    Principal,
    RequestContext,
    resolve_principal,
)

if TYPE_CHECKING:
    from fastapi import WebSocket
    from sqlalchemy.ext.asyncio import AsyncSession


def build_ws_request_context(websocket: WebSocket) -> RequestContext:
    """Construct a :class:`RequestContext` from the upgrade.

    The auth chain doesn't know about WebSockets — it works
    against headers / cookies / query_params dicts. This helper
    extracts those from the Starlette WebSocket and hands them
    over."""
    return RequestContext(
        headers=dict(websocket.headers),
        query_params=dict(websocket.query_params),
        cookies=dict(websocket.cookies),
    )


async def authenticate_upgrade(
    websocket: WebSocket,
    *,
    session: AsyncSession,
    chain_config: ChainConfig | None = None,
) -> Principal | None:
    """Resolve the caller via the FR-022 chain. Returns the
    principal, or ``None`` if no method matched."""
    context = build_ws_request_context(websocket)
    return await resolve_principal(
        session, request=context, config=chain_config
    )


__all__ = ["authenticate_upgrade", "build_ws_request_context"]
