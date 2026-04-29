"""API-key service tests — FR-005/006/007/008/009/009a."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_USER,
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    ApiKey,
    ApiKeyExpiredError,
    ApiKeyInvalidError,
    User,
    create_api_key,
    hash_password,
    list_api_keys_for_user,
    resolve_api_key,
    revoke_api_key,
    touch_api_key,
)


async def _seed_user(
    session: AsyncSession, *, role: str = ROLE_USER, is_active: bool = True
) -> User:
    u = User(
        username="alice",
        role=role,
        is_active=is_active,
        hashed_password=hash_password("x"),
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_create_api_key_default_scopes(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(async_session, user=user, name="Notifiarr")
    assert created.plaintext.startswith("rmk_")
    assert created.scopes == [SCOPE_READ]
    # Hash + prefix landed in the row.
    row = (
        await async_session.execute(select(ApiKey).where(ApiKey.id == created.api_key_id))
    ).scalar_one()
    assert row.key_prefix == created.key_prefix


async def test_create_api_key_admin_scopes(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session, role=ROLE_ADMIN)
    created = await create_api_key(
        async_session,
        user=user,
        name="Admin",
        scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
    )
    assert set(created.scopes) == {SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN}


async def test_create_api_key_dedups_scopes(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(
        async_session,
        user=user,
        name="x",
        scopes=[SCOPE_READ, SCOPE_READ, SCOPE_WRITE],
    )
    assert created.scopes == [SCOPE_READ, SCOPE_WRITE]


async def test_create_api_key_rejects_unknown_scope(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    with pytest.raises(ValueError, match="unknown scope"):
        await create_api_key(
            async_session, user=user, name="x", scopes=["godmode"]
        )


async def test_create_api_key_rejects_empty_scopes(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    with pytest.raises(ValueError, match="scopes_required"):
        await create_api_key(async_session, user=user, name="x", scopes=[])


async def test_create_api_key_rejects_empty_name(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    with pytest.raises(ValueError):
        await create_api_key(async_session, user=user, name=" ")


async def test_resolve_api_key_round_trip(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(async_session, user=user, name="x")
    resolved = await resolve_api_key(async_session, plaintext=created.plaintext)
    assert resolved.user.id == user.id
    assert resolved.scopes == [SCOPE_READ]


async def test_resolve_api_key_wrong_key(async_session: AsyncSession) -> None:
    with pytest.raises(ApiKeyInvalidError):
        await resolve_api_key(async_session, plaintext="rmk_nope")


async def test_resolve_api_key_empty(async_session: AsyncSession) -> None:
    with pytest.raises(ApiKeyInvalidError):
        await resolve_api_key(async_session, plaintext="")


async def test_resolve_api_key_expired(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    past = datetime.now(UTC) - timedelta(days=1)
    created = await create_api_key(
        async_session, user=user, name="x", expires_at=past
    )
    with pytest.raises(ApiKeyExpiredError):
        await resolve_api_key(async_session, plaintext=created.plaintext)


async def test_resolve_api_key_owner_deactivated(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(async_session, user=user, name="x")
    user.is_active = False
    await async_session.commit()
    with pytest.raises(ApiKeyInvalidError):
        await resolve_api_key(async_session, plaintext=created.plaintext)


async def test_revoke_api_key(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(async_session, user=user, name="x")
    assert await revoke_api_key(async_session, api_key_id=created.api_key_id) is True
    with pytest.raises(ApiKeyInvalidError):
        await resolve_api_key(async_session, plaintext=created.plaintext)
    # Idempotent.
    assert await revoke_api_key(async_session, api_key_id=created.api_key_id) is False


async def test_touch_api_key_updates_last_used(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_api_key(async_session, user=user, name="x")
    await touch_api_key(
        async_session, api_key_id=created.api_key_id, ip_address="192.168.1.5"
    )
    row = (
        await async_session.execute(
            select(ApiKey).where(ApiKey.id == created.api_key_id)
        )
    ).scalar_one()
    assert row.last_used_at is not None
    assert row.last_used_ip == "192.168.1.5"


async def test_list_api_keys_for_user(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    await create_api_key(async_session, user=user, name="A")
    await create_api_key(async_session, user=user, name="B")
    keys = await list_api_keys_for_user(async_session, user_id=user.id)
    assert {k.name for k in keys} == {"A", "B"}
