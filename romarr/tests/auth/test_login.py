"""Forms login service tests — FR-010."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_USER,
    InvalidCredentialsError,
    User,
    UserDeactivatedError,
    authenticate,
    hash_password,
)


async def _seed(
    session: AsyncSession,
    *,
    username: str = "alice",
    password: str | None = "goodpassword",
    is_active: bool = True,
) -> User:
    u = User(
        username=username,
        role=ROLE_USER,
        is_active=is_active,
        hashed_password=hash_password(password) if password else None,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_authenticate_happy_path(async_session: AsyncSession) -> None:
    await _seed(async_session)
    user = await authenticate(async_session, username="alice", password="goodpassword")
    assert user.username == "alice"
    assert user.role == ROLE_USER


async def test_authenticate_wrong_password(async_session: AsyncSession) -> None:
    await _seed(async_session)
    with pytest.raises(InvalidCredentialsError):
        await authenticate(async_session, username="alice", password="WRONG")


async def test_authenticate_unknown_user(async_session: AsyncSession) -> None:
    """Same exception class as wrong-password — no user-enumeration oracle."""
    with pytest.raises(InvalidCredentialsError):
        await authenticate(async_session, username="bob", password="anything")


async def test_authenticate_oidc_only_user_rejected(async_session: AsyncSession) -> None:
    """A user with no hashed_password (OIDC-only) cannot use forms login."""
    await _seed(async_session, password=None)
    with pytest.raises(InvalidCredentialsError):
        await authenticate(async_session, username="alice", password="anything")


async def test_authenticate_deactivated_user(async_session: AsyncSession) -> None:
    await _seed(async_session, is_active=False)
    with pytest.raises(UserDeactivatedError):
        await authenticate(
            async_session, username="alice", password="goodpassword"
        )


async def test_authenticate_empty_args_rejected(async_session: AsyncSession) -> None:
    with pytest.raises(InvalidCredentialsError):
        await authenticate(async_session, username="", password="x")
    with pytest.raises(InvalidCredentialsError):
        await authenticate(async_session, username="alice", password="")
