"""Auth chain resolver — FR-022 (clarified, JWT dropped).

Resolution order (clarified Q3 of spec 010):
  1. ``X-Api-Key`` header  → API key lookup
  2. ``apikey`` query param → API key lookup
  3. session cookie         → :func:`resolve_session`
  4. trusted-proxy header   → username lookup (when feature enabled)

The first method that succeeds wins. When all four miss, the
caller is unauthenticated (the chain returns ``None``; the upstream
guard lifts that to a 401 with the generic ``unauthenticated``
reason per FR-023).

Per FR-023 the resolver MUST NOT leak which method was attempted —
on a no-match outcome it returns ``None`` regardless of whether
the caller supplied a malformed cookie or a wrong API key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.auth.api_keys import resolve_api_key
from romarr.auth.errors import AuthError
from romarr.auth.models import User
from romarr.auth.permissions import Principal
from romarr.auth.sessions import resolve_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ChainConfig:
    """Configuration for :func:`resolve_principal`.

    ``trust_proxy_auth`` mirrors ``ROMARR_TRUST_PROXY_AUTH`` from
    spec 010 FR-017 — when False, the trusted-proxy step is a no-op.

    ``trusted_headers`` lists the request headers that carry the
    proxy-supplied username. Default per FR-017:
    ``["X-Authentik-Username", "X-Forwarded-User", "Remote-User"]``.
    """

    trust_proxy_auth: bool = False
    trusted_headers: tuple[str, ...] = (
        "X-Authentik-Username",
        "X-Forwarded-User",
        "Remote-User",
    )


@dataclass(frozen=True, slots=True)
class _RequestContext:
    """Shape consumers pass into :func:`resolve_principal`.

    Lives in this module so the auth layer doesn't depend on
    FastAPI / Starlette. The HTTP layer (next slice) builds one of
    these from the incoming Request.
    """

    headers: Mapping[str, str]
    query_params: Mapping[str, str]
    cookies: Mapping[str, str]


# Public re-export so endpoint code can construct contexts cleanly.
RequestContext = _RequestContext


SESSION_COOKIE_NAME: str = "romarr_session"
"""Default cookie name. Override via :class:`ChainConfig` if needed."""


async def resolve_principal(
    session: AsyncSession,
    *,
    request: RequestContext,
    config: ChainConfig | None = None,
) -> Principal | None:
    """Walk the FR-022 chain and return the first successful Principal.

    Returns ``None`` when every method is missing or fails — the
    upstream guard lifts that to a 401 ``unauthenticated``.
    """
    cfg = config or ChainConfig()

    # 1. X-Api-Key header
    api_key_value = request.headers.get("X-Api-Key") or request.headers.get("x-api-key")
    if api_key_value:
        principal = await _try_api_key(session, plaintext=api_key_value)
        if principal is not None:
            return principal

    # 2. apikey query param
    qp_value = request.query_params.get("apikey")
    if qp_value:
        principal = await _try_api_key(session, plaintext=qp_value)
        if principal is not None:
            return principal

    # 3. session cookie
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_value:
        principal = await _try_session(session, session_id=cookie_value)
        if principal is not None:
            return principal

    # 4. trusted-proxy header (gated by configuration)
    if cfg.trust_proxy_auth:
        for header in cfg.trusted_headers:
            value = request.headers.get(header) or request.headers.get(header.lower())
            if value:
                principal = await _try_proxy_user(session, username=value)
                if principal is not None:
                    return principal

    return None


# ---------------------------------------------------------------------------
# Per-method helpers — each returns Principal | None and never raises.
# ---------------------------------------------------------------------------


async def _try_api_key(
    session: AsyncSession, *, plaintext: str
) -> Principal | None:
    try:
        resolved = await resolve_api_key(session, plaintext=plaintext)
    except AuthError:
        return None
    return Principal(
        user_id=resolved.user.id,
        username=resolved.user.username,
        role=resolved.user.role,
        api_key_scopes=resolved.scopes,
    )


async def _try_session(
    session: AsyncSession, *, session_id: str
) -> Principal | None:
    try:
        resolved = await resolve_session(session, session_id=session_id)
    except AuthError:
        return None
    return Principal(
        user_id=resolved.user.id,
        username=resolved.user.username,
        role=resolved.user.role,
        api_key_scopes=None,
    )


async def _try_proxy_user(
    session: AsyncSession, *, username: str
) -> Principal | None:
    """Resolve a trusted-proxy username to a Principal.

    Spec 010 FR-018 says: a username that does not match any existing
    user MUST be auto-created with role ``user`` (configurable
    default). For now, the auto-create lives in a follow-up slice;
    this function only resolves an *existing* user.
    """
    if not username:
        return None
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        api_key_scopes=None,
    )
