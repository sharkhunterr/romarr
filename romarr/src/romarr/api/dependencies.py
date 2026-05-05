"""Reusable FastAPI dependencies.

The dependency graph for an authenticated request looks like:

    Request
      │
      ├── get_db() ──────────────► AsyncSession
      │
      ├── get_request_context() ─► RequestContext
      │
      └── get_current_principal() ► Principal | None
              │
              └── require_role(role) ► Principal (raises 401/403 on miss)

Each layer is its own dependency so endpoint signatures stay clean
and tests can override any one of them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

# AsyncSession is imported at runtime — FastAPI introspects
# ``Annotated[AsyncSession, Depends(...)]`` to build the OpenAPI
# schema, so the symbol must be live (TYPE_CHECKING-only imports
# break ``/api/v3/openapi.json`` generation).
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    ChainConfig,
    IpRateLimiter,
    Principal,
    RequestContext,
    require_role,
    resolve_principal,
)
from romarr.auth import touch_api_key as _touch_api_key

# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a per-request AsyncSession bound to the app's engine."""
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield session


def get_event_channel(request: Request):  # type: ignore[no-untyped-def]
    """Return the app-wide :class:`EventChannel` (spec 011) or
    None when the lifespan hasn't constructed one (test
    harnesses that build the app without entering it as a
    context manager).

    Routes that produce events publish through this channel; the
    WS bridge fans out to live operator sessions automatically
    (spec 013 T068 / T072).
    """
    return getattr(request.app.state, "event_channel", None)


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the app-wide sessionmaker for callers that need a fresh
    session OUTSIDE the per-request transaction (e.g. spec 003's
    ``fail_log`` audit-row writer that runs after the ingest rollback)."""
    sessionmaker: async_sessionmaker[AsyncSession] = (
        request.app.state.db_sessionmaker
    )
    return sessionmaker


# ---------------------------------------------------------------------------
# Request context (headers + query + cookies — what the chain reads)
# ---------------------------------------------------------------------------


def get_request_context(request: Request) -> RequestContext:
    """Build a chain-shaped :class:`RequestContext` from a FastAPI Request."""
    return RequestContext(
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        cookies=dict(request.cookies),
    )


# ---------------------------------------------------------------------------
# Chain config — read once per app
# ---------------------------------------------------------------------------


def get_chain_config(request: Request) -> ChainConfig:
    """Per-app :class:`ChainConfig`, defaulting to no-trust-proxy.

    Tests override via ``app.dependency_overrides`` rather than
    mutating env vars at import time.
    """
    cfg: ChainConfig | None = getattr(request.app.state, "auth_chain_config", None)
    return cfg if cfg is not None else ChainConfig()


# ---------------------------------------------------------------------------
# Current principal (None when unauthenticated)
# ---------------------------------------------------------------------------


async def get_current_principal(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    chain_config: Annotated[ChainConfig, Depends(get_chain_config)],
) -> Principal | None:
    """Resolve the caller via the FR-022 chain.

    Returns ``None`` when no method matches — the upstream guard
    lifts that to a 401 ``unauthenticated`` per FR-023.

    Side effect: when authenticated via API key, schedules a
    best-effort ``last_used_at`` / ``last_used_ip`` update (FR-027).
    Failures inside the touch are swallowed so they can never
    affect the request outcome.
    """
    principal = await resolve_principal(
        db, request=context, config=chain_config
    )
    if principal is not None and principal.via_api_key:
        # The chain doesn't know which api_key row resolved (it
        # returned just the Principal); we look that up via the
        # request context's apikey value.  See FR-027 — best effort,
        # never raises.
        api_key_value = context.headers.get("X-Api-Key") or context.headers.get(
            "x-api-key"
        ) or context.query_params.get("apikey")
        if api_key_value is not None:
            from romarr.auth.api_keys import resolve_api_key

            try:
                resolved = await resolve_api_key(db, plaintext=api_key_value)
                await _touch_api_key(
                    db,
                    api_key_id=resolved.api_key_id,
                    ip_address=request.client.host if request.client else None,
                )
            except Exception:
                pass
    return principal


# ---------------------------------------------------------------------------
# require_role guards (one per RBAC tier)
# ---------------------------------------------------------------------------


_RoleGuard = Callable[..., Awaitable[Principal]]


def _make_role_guard(required_role: str) -> _RoleGuard:
    async def _guard(
        principal: Annotated[
            Principal | None, Depends(get_current_principal)
        ],
    ) -> Principal:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "errorMessage": "unauthenticated",
                    "errorCode": "unauthenticated",
                },
                headers={"WWW-Authenticate": "Cookie"},
            )
        if not require_role(principal, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "errorMessage": "permission_denied",
                    "errorCode": "permission_denied",
                },
            )
        return principal

    _guard.__name__ = f"require_role_{required_role}"
    return _guard


require_readonly = _make_role_guard(ROLE_READONLY)
require_user = _make_role_guard(ROLE_USER)
require_admin = _make_role_guard(ROLE_ADMIN)


# ---------------------------------------------------------------------------
# Per-IP rate limiter (FR-010a) — single shared instance per app
# ---------------------------------------------------------------------------


def get_login_rate_limiter(request: Request) -> IpRateLimiter:
    """Return the app-scoped IpRateLimiter, creating it on first use."""
    limiter: IpRateLimiter | None = getattr(
        request.app.state, "login_rate_limiter", None
    )
    if limiter is None:
        limiter = IpRateLimiter()
        request.app.state.login_rate_limiter = limiter
    return limiter


def client_ip(request: Request) -> str:
    """Extract the caller IP, honouring ``X-Forwarded-For`` first hop.

    The /auth/* rate limit is per-IP so a reverse proxy must surface
    the original IP via X-Forwarded-For (the standard *arr deployment
    pattern). When no header is present, fall back to the immediate
    client.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # First entry is the original client; later entries are proxies.
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
