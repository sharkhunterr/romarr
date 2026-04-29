"""Auth chain resolver + permissions tests — FR-022 / FR-024."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    SCOPE_READ,
    SCOPE_WRITE,
    ChainConfig,
    Principal,
    RequestContext,
    User,
    create_api_key,
    create_session,
    hash_password,
    require_role,
    resolve_principal,
)


async def _seed(
    session: AsyncSession,
    *,
    username: str = "alice",
    role: str = ROLE_USER,
    is_active: bool = True,
) -> User:
    u = User(
        username=username,
        role=role,
        is_active=is_active,
        hashed_password=hash_password("x"),
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _ctx(
    *,
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> RequestContext:
    return RequestContext(
        headers=headers or {},
        query_params=query_params or {},
        cookies=cookies or {},
    )


# ---------------------------------------------------------------------------
# Auth chain (FR-022)
# ---------------------------------------------------------------------------


async def test_chain_resolves_via_x_api_key_header(async_session: AsyncSession) -> None:
    user = await _seed(async_session)
    created = await create_api_key(async_session, user=user, name="x")

    principal = await resolve_principal(
        async_session, request=_ctx(headers={"X-Api-Key": created.plaintext})
    )
    assert principal is not None
    assert principal.user_id == user.id
    assert principal.via_api_key is True
    assert principal.api_key_scopes == [SCOPE_READ]


async def test_chain_resolves_via_apikey_query_param(async_session: AsyncSession) -> None:
    user = await _seed(async_session)
    created = await create_api_key(async_session, user=user, name="x")

    principal = await resolve_principal(
        async_session, request=_ctx(query_params={"apikey": created.plaintext})
    )
    assert principal is not None
    assert principal.user_id == user.id


async def test_chain_resolves_via_session_cookie(async_session: AsyncSession) -> None:
    user = await _seed(async_session)
    created = await create_session(async_session, user=user)

    principal = await resolve_principal(
        async_session, request=_ctx(cookies={"romarr_session": created.session_id})
    )
    assert principal is not None
    assert principal.user_id == user.id
    assert principal.via_api_key is False


async def test_chain_returns_none_when_no_credential(
    async_session: AsyncSession,
) -> None:
    principal = await resolve_principal(async_session, request=_ctx())
    assert principal is None


async def test_chain_returns_none_for_garbage_credentials(
    async_session: AsyncSession,
) -> None:
    """FR-023: no leak about which method failed."""
    principal = await resolve_principal(
        async_session,
        request=_ctx(
            headers={"X-Api-Key": "rmk_nope"},
            cookies={"romarr_session": "alsonope"},
        ),
    )
    assert principal is None


async def test_chain_api_key_wins_over_cookie(async_session: AsyncSession) -> None:
    """FR-022 ordering: API key beats cookie when both are present."""
    api_user = await _seed(async_session, username="api_user", role=ROLE_USER)
    cookie_user = await _seed(
        async_session, username="cookie_user", role=ROLE_ADMIN
    )
    api_key = await create_api_key(async_session, user=api_user, name="x")
    cookie = await create_session(async_session, user=cookie_user)

    principal = await resolve_principal(
        async_session,
        request=_ctx(
            headers={"X-Api-Key": api_key.plaintext},
            cookies={"romarr_session": cookie.session_id},
        ),
    )
    assert principal is not None
    assert principal.username == "api_user"  # API key won


async def test_chain_proxy_auth_disabled_by_default(
    async_session: AsyncSession,
) -> None:
    await _seed(async_session)
    principal = await resolve_principal(
        async_session,
        request=_ctx(headers={"X-Authentik-Username": "alice"}),
    )
    # No config → trust_proxy_auth defaults to False → header ignored.
    assert principal is None


async def test_chain_proxy_auth_resolves_when_enabled(
    async_session: AsyncSession,
) -> None:
    await _seed(async_session)
    principal = await resolve_principal(
        async_session,
        request=_ctx(headers={"X-Authentik-Username": "alice"}),
        config=ChainConfig(trust_proxy_auth=True),
    )
    assert principal is not None
    assert principal.username == "alice"
    assert principal.via_api_key is False


async def test_chain_proxy_auth_requires_active_user(
    async_session: AsyncSession,
) -> None:
    await _seed(async_session, is_active=False)
    principal = await resolve_principal(
        async_session,
        request=_ctx(headers={"X-Authentik-Username": "alice"}),
        config=ChainConfig(trust_proxy_auth=True),
    )
    assert principal is None  # deactivated → no principal


# ---------------------------------------------------------------------------
# Permission guards (FR-024)
# ---------------------------------------------------------------------------


def test_require_role_admin_passes_lower_tiers() -> None:
    p = Principal(user_id=1, username="a", role=ROLE_ADMIN)
    assert require_role(p, ROLE_ADMIN) is True
    assert require_role(p, ROLE_USER) is True
    assert require_role(p, ROLE_READONLY) is True


def test_require_role_user_blocked_from_admin() -> None:
    p = Principal(user_id=1, username="a", role=ROLE_USER)
    assert require_role(p, ROLE_ADMIN) is False
    assert require_role(p, ROLE_USER) is True
    assert require_role(p, ROLE_READONLY) is True


def test_require_role_readonly_only_passes_readonly() -> None:
    p = Principal(user_id=1, username="a", role=ROLE_READONLY)
    assert require_role(p, ROLE_READONLY) is True
    assert require_role(p, ROLE_USER) is False
    assert require_role(p, ROLE_ADMIN) is False


def test_require_role_unauthenticated() -> None:
    assert require_role(None, ROLE_READONLY) is False


def test_require_role_api_key_with_admin_role_but_only_read_scope_blocked() -> None:
    """A user with admin role using an API key without the admin scope is blocked.

    FR-009a — for API-key principals the scope check applies on top
    of the role check.
    """
    p = Principal(
        user_id=1,
        username="a",
        role=ROLE_ADMIN,
        api_key_scopes=[SCOPE_READ],
    )
    assert require_role(p, ROLE_ADMIN) is False  # role passes, scope fails
    assert require_role(p, ROLE_READONLY) is True


def test_require_role_api_key_with_admin_scope_passes_everything() -> None:
    p = Principal(
        user_id=1,
        username="a",
        role=ROLE_ADMIN,
        api_key_scopes=["admin"],
    )
    assert require_role(p, ROLE_ADMIN) is True
    assert require_role(p, ROLE_USER) is True
    assert require_role(p, ROLE_READONLY) is True


def test_require_role_api_key_with_write_scope_blocks_admin_endpoint() -> None:
    p = Principal(
        user_id=1,
        username="a",
        role=ROLE_ADMIN,
        api_key_scopes=[SCOPE_WRITE],
    )
    assert require_role(p, ROLE_ADMIN) is False  # admin role passes, but write scope insufficient
    assert require_role(p, ROLE_USER) is True
    assert require_role(p, ROLE_READONLY) is True


# Suppress unused-import warning — pytest fixture machinery picks them up.
_ = pytest
