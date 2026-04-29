"""Session service tests — FR-012a sliding TTL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_USER,
    Session,
    SessionExpiredError,
    SessionNotFoundError,
    User,
    create_session,
    hash_password,
    resolve_session,
    revoke_all_for_user,
    revoke_session,
)


async def _seed_user(session: AsyncSession, *, is_active: bool = True) -> User:
    u = User(
        username="alice",
        role=ROLE_USER,
        is_active=is_active,
        hashed_password=hash_password("x"),
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_create_session_returns_plaintext_id_and_30d_expiry(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)
    assert created.session_id  # url-safe random string
    assert (created.expires_at - datetime.now(UTC)).days == 29  # ≈ 30
    # Verify the row landed.
    row = (
        await async_session.execute(
            select(Session).where(Session.id == created.session_id)
        )
    ).scalar_one()
    assert row.user_id == user.id


async def test_resolve_session_slides_expiry_forward(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)

    # Manually set expires_at to a near-future value so we can confirm sliding.
    near = datetime.now(UTC) + timedelta(days=1)
    row = (
        await async_session.execute(select(Session).where(Session.id == created.session_id))
    ).scalar_one()
    row.expires_at = near
    row.last_used_at = datetime.now(UTC) - timedelta(days=29)
    await async_session.commit()

    resolved = await resolve_session(async_session, session_id=created.session_id)
    assert resolved.user.id == user.id
    # After resolve, expires_at should be ~30 days out again.
    assert (resolved.expires_at - datetime.now(UTC)).days >= 29


async def test_resolve_session_no_slide(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)
    raw_expiry = (
        await async_session.execute(select(Session).where(Session.id == created.session_id))
    ).scalar_one().expires_at
    # SQLite drops tzinfo on read; coerce to compare apples-to-apples.
    fixed_expiry = (
        raw_expiry if raw_expiry.tzinfo is not None else raw_expiry.replace(tzinfo=UTC)
    )

    resolved = await resolve_session(
        async_session, session_id=created.session_id, slide=False
    )
    assert resolved.expires_at == fixed_expiry


async def test_resolve_session_expired_raises_and_cleans_up(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)

    row = (
        await async_session.execute(
            select(Session).where(Session.id == created.session_id)
        )
    ).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await async_session.commit()

    with pytest.raises(SessionExpiredError):
        await resolve_session(async_session, session_id=created.session_id)

    # Expired row was cleaned up.
    rows = (await async_session.execute(select(Session))).scalars().all()
    assert rows == []


async def test_resolve_session_not_found(async_session: AsyncSession) -> None:
    with pytest.raises(SessionNotFoundError):
        await resolve_session(async_session, session_id="nope")
    with pytest.raises(SessionNotFoundError):
        await resolve_session(async_session, session_id="")


async def test_resolve_session_deactivated_user_cleans_up(
    async_session: AsyncSession,
) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)

    user.is_active = False
    await async_session.commit()

    with pytest.raises(SessionExpiredError):
        await resolve_session(async_session, session_id=created.session_id)


async def test_revoke_session_removes_row(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    created = await create_session(async_session, user=user)

    assert await revoke_session(async_session, session_id=created.session_id) is True
    rows = (await async_session.execute(select(Session))).scalars().all()
    assert rows == []
    # Idempotent — second revoke returns False but doesn't raise.
    assert await revoke_session(async_session, session_id=created.session_id) is False


async def test_revoke_all_for_user(async_session: AsyncSession) -> None:
    user = await _seed_user(async_session)
    await create_session(async_session, user=user)
    await create_session(async_session, user=user)
    await create_session(async_session, user=user)
    count = await revoke_all_for_user(async_session, user_id=user.id)
    assert count == 3
    assert (await async_session.execute(select(Session))).scalars().all() == []
