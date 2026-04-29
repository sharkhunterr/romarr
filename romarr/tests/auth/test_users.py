"""User service tests — admin CRUD + trusted-proxy auto-create."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    User,
    create_session,
    hash_password,
)
from romarr.auth.users import (
    CannotDeleteLastAdminError,
    UserCreateError,
    create_user,
    delete_user,
    get_or_auto_create_proxy_user,
    list_users,
    update_user,
)

# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_user_with_password(async_session: AsyncSession) -> None:
    user = await create_user(
        async_session, username="alice", password="goodpassword", role=ROLE_USER
    )
    assert user.id is not None
    assert user.role == ROLE_USER
    assert user.hashed_password is not None  # bcrypt hash


async def test_create_user_oidc_only_no_password(async_session: AsyncSession) -> None:
    user = await create_user(
        async_session, username="alice", password=None, role=ROLE_USER
    )
    assert user.hashed_password is None


async def test_create_user_unknown_role_rejected(async_session: AsyncSession) -> None:
    with pytest.raises(UserCreateError) as exc:
        await create_user(
            async_session, username="alice", password="x", role="emperor"
        )
    assert exc.value.code == "validation_failed"


async def test_create_user_duplicate_username_rejected(
    async_session: AsyncSession,
) -> None:
    await create_user(async_session, username="alice", password="x")
    with pytest.raises(UserCreateError) as exc:
        await create_user(async_session, username="alice", password="x")
    assert exc.value.code == "username_taken"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_update_user_role(async_session: AsyncSession) -> None:
    u = await create_user(
        async_session, username="alice", password="x", role=ROLE_USER
    )
    updated = await update_user(async_session, user_id=u.id, role=ROLE_ADMIN)
    assert updated.role == ROLE_ADMIN


async def test_update_user_reject_unknown_role(async_session: AsyncSession) -> None:
    u = await create_user(async_session, username="alice", password="x")
    with pytest.raises(UserCreateError) as exc:
        await update_user(async_session, user_id=u.id, role="emperor")
    assert exc.value.code == "validation_failed"


async def test_update_user_cannot_demote_lone_admin(
    async_session: AsyncSession,
) -> None:
    admin = await create_user(
        async_session, username="admin", password="x", role=ROLE_ADMIN
    )
    with pytest.raises(CannotDeleteLastAdminError):
        await update_user(async_session, user_id=admin.id, role=ROLE_USER)


async def test_update_user_can_demote_when_other_admin_exists(
    async_session: AsyncSession,
) -> None:
    admin1 = await create_user(
        async_session, username="admin1", password="x", role=ROLE_ADMIN
    )
    await create_user(
        async_session, username="admin2", password="x", role=ROLE_ADMIN
    )
    updated = await update_user(async_session, user_id=admin1.id, role=ROLE_USER)
    assert updated.role == ROLE_USER


async def test_update_user_deactivate_revokes_sessions(
    async_session: AsyncSession,
) -> None:
    u = await create_user(async_session, username="alice", password="x")
    await create_session(async_session, user=u)
    await create_session(async_session, user=u)

    await update_user(async_session, user_id=u.id, is_active=False)
    # Sessions table has been cleared for this user.
    from sqlalchemy import select

    from romarr.auth.models import Session as SessionRow

    rows = (await async_session.execute(select(SessionRow))).scalars().all()
    assert rows == []


async def test_update_user_unknown_id_returns_not_found(
    async_session: AsyncSession,
) -> None:
    with pytest.raises(UserCreateError) as exc:
        await update_user(async_session, user_id=9999, role=ROLE_USER)
    assert exc.value.code == "not_found"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_user_succeeds(async_session: AsyncSession) -> None:
    u = await create_user(async_session, username="alice", password="x")
    assert await delete_user(async_session, user_id=u.id) is True
    # Idempotent miss returns False.
    assert await delete_user(async_session, user_id=u.id) is False


async def test_delete_lone_admin_refused(async_session: AsyncSession) -> None:
    admin = await create_user(
        async_session, username="admin", password="x", role=ROLE_ADMIN
    )
    with pytest.raises(CannotDeleteLastAdminError):
        await delete_user(async_session, user_id=admin.id)


async def test_delete_system_sentinel_refused(async_session: AsyncSession) -> None:
    async_session.add(
        User(
            id=0,
            username="system",
            role=ROLE_ADMIN,
            is_active=False,
        )
    )
    await async_session.commit()
    with pytest.raises(CannotDeleteLastAdminError):
        await delete_user(async_session, user_id=0)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_users_excludes_system_by_default(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        User(id=0, username="system", role=ROLE_ADMIN, is_active=False)
    )
    await async_session.commit()
    await create_user(async_session, username="alice", password="x")
    await create_user(async_session, username="bob", password="x")

    rows = await list_users(async_session)
    usernames = {r.username for r in rows}
    assert "system" not in usernames
    assert {"alice", "bob"}.issubset(usernames)


async def test_list_users_include_system_when_asked(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        User(id=0, username="system", role=ROLE_ADMIN, is_active=False)
    )
    await async_session.commit()
    rows = await list_users(async_session, include_system=True)
    assert any(r.username == "system" for r in rows)


# ---------------------------------------------------------------------------
# Trusted-proxy auto-create (FR-018)
# ---------------------------------------------------------------------------


async def test_get_or_auto_create_proxy_user_creates_on_first_contact(
    async_session: AsyncSession,
) -> None:
    user = await get_or_auto_create_proxy_user(
        async_session, username="alice"
    )
    assert user.role == ROLE_USER  # default
    assert user.is_active is True
    assert user.hashed_password is None  # OIDC/proxy-only


async def test_get_or_auto_create_proxy_user_returns_existing(
    async_session: AsyncSession,
) -> None:
    existing = await create_user(
        async_session, username="alice", password=None, role=ROLE_ADMIN
    )
    user = await get_or_auto_create_proxy_user(
        async_session, username="alice"
    )
    assert user.id == existing.id
    assert user.role == ROLE_ADMIN  # not overwritten


async def test_get_or_auto_create_proxy_user_custom_default_role(
    async_session: AsyncSession,
) -> None:
    user = await get_or_auto_create_proxy_user(
        async_session, username="alice", default_role=ROLE_READONLY
    )
    assert user.role == ROLE_READONLY


async def test_get_or_auto_create_proxy_user_unknown_role_rejected(
    async_session: AsyncSession,
) -> None:
    with pytest.raises(UserCreateError):
        await get_or_auto_create_proxy_user(
            async_session, username="alice", default_role="emperor"
        )


# ---------------------------------------------------------------------------
# Chain integration — auto-create through the FR-022 resolver
# ---------------------------------------------------------------------------


async def test_chain_proxy_auth_auto_creates_user(
    async_session: AsyncSession,
) -> None:
    """End-to-end: trusted-proxy header → user auto-created at first contact."""
    from romarr.auth import (
        ChainConfig,
        RequestContext,
        resolve_principal,
    )

    principal = await resolve_principal(
        async_session,
        request=RequestContext(
            headers={"X-Authentik-Username": "alice"},
            query_params={},
            cookies={},
        ),
        config=ChainConfig(trust_proxy_auth=True, auto_create_proxy_users=True),
    )
    assert principal is not None
    assert principal.username == "alice"
    assert principal.role == ROLE_USER  # default

    # Second call returns the same user.
    second = await resolve_principal(
        async_session,
        request=RequestContext(
            headers={"X-Authentik-Username": "alice"},
            query_params={},
            cookies={},
        ),
        config=ChainConfig(trust_proxy_auth=True),
    )
    assert second is not None
    assert second.user_id == principal.user_id


async def test_chain_proxy_auth_no_auto_create_when_disabled(
    async_session: AsyncSession,
) -> None:
    """Per FR-018: auto-create can be turned off."""
    from romarr.auth import (
        ChainConfig,
        RequestContext,
        resolve_principal,
    )

    principal = await resolve_principal(
        async_session,
        request=RequestContext(
            headers={"X-Authentik-Username": "ghost"},
            query_params={},
            cookies={},
        ),
        config=ChainConfig(
            trust_proxy_auth=True, auto_create_proxy_users=False
        ),
    )
    assert principal is None


async def test_chain_proxy_auth_deactivated_user_blocked(
    async_session: AsyncSession,
) -> None:
    """A deactivated user with a matching proxy header is NOT reactivated."""
    from romarr.auth import (
        ChainConfig,
        RequestContext,
        resolve_principal,
    )

    async_session.add(
        User(
            username="alice",
            role=ROLE_USER,
            is_active=False,
            hashed_password=hash_password("x"),
        )
    )
    await async_session.commit()

    principal = await resolve_principal(
        async_session,
        request=RequestContext(
            headers={"X-Authentik-Username": "alice"},
            query_params={},
            cookies={},
        ),
        config=ChainConfig(trust_proxy_auth=True, auto_create_proxy_users=True),
    )
    assert principal is None
