"""Auth ORM model tests — FR-001 / FR-002 / FR-009a / FR-012a."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    ApiKey,
    Session,
    SetupToken,
    User,
    generate_api_key,
    hash_password,
)

# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


async def test_user_persists_with_role(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_USER, hashed_password=hash_password("x"))
    async_session.add(u)
    await async_session.flush()
    assert u.id is not None
    assert u.role == ROLE_USER
    # Property derivation per the clarified FR-002.
    assert u.is_superuser is False


async def test_user_admin_role_implies_is_superuser(async_session: AsyncSession) -> None:
    admin = User(username="admin", role=ROLE_ADMIN, hashed_password=hash_password("x"))
    async_session.add(admin)
    await async_session.flush()
    assert admin.is_superuser is True


async def test_user_username_unique(async_session: AsyncSession) -> None:
    async_session.add(User(username="alice", role=ROLE_USER))
    await async_session.flush()
    async_session.add(User(username="alice", role=ROLE_USER))
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_user_email_unique_when_set(async_session: AsyncSession) -> None:
    async_session.add(
        User(username="alice", email="a@example.com", role=ROLE_USER)
    )
    await async_session.flush()
    async_session.add(
        User(username="bob", email="a@example.com", role=ROLE_USER)
    )
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_user_role_check_constraint(async_session: AsyncSession) -> None:
    """role MUST be one of admin/user/readonly per CHECK constraint."""
    async_session.add(User(username="alice", role="something_else"))
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_user_oidc_identity_unique(async_session: AsyncSession) -> None:
    async_session.add(
        User(
            username="alice",
            oidc_provider="authentik",
            oidc_subject="abc-123",
            role=ROLE_USER,
        )
    )
    await async_session.flush()
    async_session.add(
        User(
            username="alice2",
            oidc_provider="authentik",
            oidc_subject="abc-123",
            role=ROLE_USER,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_user_readonly_role_property_false(async_session: AsyncSession) -> None:
    u = User(username="reader", role=ROLE_READONLY)
    async_session.add(u)
    await async_session.flush()
    assert u.is_superuser is False


async def test_user_no_is_superuser_column(async_session: AsyncSession) -> None:
    """The schema MUST NOT carry an is_superuser column."""
    from sqlalchemy import inspect

    user_cols = {c.name for c in inspect(User).columns}
    assert "is_superuser" not in user_cols


# ---------------------------------------------------------------------------
# Session — FR-012a sliding TTL
# ---------------------------------------------------------------------------


async def test_session_persists_with_sliding_ttl(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_USER, hashed_password=hash_password("x"))
    async_session.add(u)
    await async_session.flush()

    now = datetime.now(UTC)
    sess = Session(
        id="a" * 64,
        user_id=u.id,
        last_used_at=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )
    async_session.add(sess)
    await async_session.flush()

    loaded = (
        await async_session.execute(
            select(Session).where(Session.id == "a" * 64)
        )
    ).scalar_one()
    assert loaded.user_id == u.id
    assert (loaded.expires_at - loaded.last_used_at).days == 30


async def test_session_cascades_on_user_delete(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_USER, hashed_password=hash_password("x"))
    async_session.add(u)
    await async_session.flush()

    now = datetime.now(UTC)
    async_session.add(
        Session(
            id="a" * 64,
            user_id=u.id,
            last_used_at=now,
            expires_at=now + timedelta(days=30),
            created_at=now,
        )
    )
    await async_session.flush()

    await async_session.delete(u)
    await async_session.flush()

    rows = (await async_session.execute(select(Session))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# ApiKey — FR-005 / FR-009a
# ---------------------------------------------------------------------------


async def test_api_key_persists_with_default_read_scope(
    async_session: AsyncSession,
) -> None:
    u = User(username="alice", role=ROLE_USER)
    async_session.add(u)
    await async_session.flush()

    _plaintext, key_hash, key_prefix = generate_api_key()
    k = ApiKey(
        user_id=u.id,
        name="Notifiarr Production",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    async_session.add(k)
    await async_session.flush()
    assert k.scopes == ["read"]


async def test_api_key_hash_unique(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_USER)
    async_session.add(u)
    await async_session.flush()

    _, key_hash, key_prefix = generate_api_key()
    async_session.add(
        ApiKey(user_id=u.id, name="A", key_hash=key_hash, key_prefix=key_prefix)
    )
    await async_session.flush()
    async_session.add(
        ApiKey(user_id=u.id, name="B", key_hash=key_hash, key_prefix=key_prefix)
    )
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_api_key_cascades_on_user_delete(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_USER)
    async_session.add(u)
    await async_session.flush()

    _, key_hash, key_prefix = generate_api_key()
    async_session.add(
        ApiKey(user_id=u.id, name="A", key_hash=key_hash, key_prefix=key_prefix)
    )
    await async_session.flush()

    await async_session.delete(u)
    await async_session.flush()

    assert (
        (await async_session.execute(select(ApiKey))).scalars().all() == []
    )


async def test_api_key_admin_scope_array(async_session: AsyncSession) -> None:
    u = User(username="alice", role=ROLE_ADMIN)
    async_session.add(u)
    await async_session.flush()

    _, key_hash, key_prefix = generate_api_key()
    k = ApiKey(
        user_id=u.id,
        name="Admin key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=["read", "write", "admin"],
    )
    async_session.add(k)
    await async_session.flush()
    await async_session.refresh(k)
    assert set(k.scopes) == {"read", "write", "admin"}


# ---------------------------------------------------------------------------
# SetupToken — FR-019
# ---------------------------------------------------------------------------


async def test_setup_token_round_trip(async_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    t = SetupToken(
        token_hash="0" * 64, expires_at=now + timedelta(hours=24)
    )
    async_session.add(t)
    await async_session.flush()
    assert t.id is not None
    assert t.consumed_at is None


async def test_setup_token_hash_unique(async_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    async_session.add(
        SetupToken(token_hash="0" * 64, expires_at=now + timedelta(hours=24))
    )
    await async_session.flush()
    async_session.add(
        SetupToken(token_hash="0" * 64, expires_at=now + timedelta(hours=24))
    )
    with pytest.raises(IntegrityError):
        await async_session.flush()
