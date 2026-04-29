"""SetupToken bootstrap tests — FR-019/020/021."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_USER,
    SetupToken,
    SetupTokenAlreadyConsumedError,
    SetupTokenExpiredError,
    SetupTokenInvalidError,
    User,
    consume_setup_token,
    hash_password,
    maybe_bootstrap_setup_token,
)


async def test_bootstrap_mints_token_on_empty_db(
    async_session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    result = await maybe_bootstrap_setup_token(async_session)
    assert result.reason == "minted"
    assert result.plaintext is not None
    assert len(result.plaintext) >= 32  # url-safe encoded random bytes
    assert result.expires_at is not None

    # The plaintext is printed to stderr exactly once with the prefix.
    captured = capsys.readouterr()
    assert "ROMARR INITIAL SETUP TOKEN" in captured.err
    assert result.plaintext in captured.err


async def test_bootstrap_skips_when_active_user_exists(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        User(username="alice", role=ROLE_USER, hashed_password=hash_password("x"))
    )
    await async_session.commit()

    result = await maybe_bootstrap_setup_token(async_session)
    assert result.reason == "skipped_users_exist"
    assert result.plaintext is None


async def test_bootstrap_skips_when_unconsumed_token_present(
    async_session: AsyncSession,
) -> None:
    """Re-bootstraps don't mint a new token when one is already pending."""
    first = await maybe_bootstrap_setup_token(async_session)
    assert first.reason == "minted"
    second = await maybe_bootstrap_setup_token(async_session)
    assert second.reason == "already_present"
    assert second.plaintext is None


async def test_bootstrap_does_not_count_system_sentinel_user(
    async_session: AsyncSession,
) -> None:
    """The id=0 'system' row is is_active=False and excluded from the population check."""
    async_session.add(
        User(
            id=0,
            username="system",
            role=ROLE_ADMIN,
            is_active=False,
            hashed_password=None,
        )
    )
    await async_session.commit()

    result = await maybe_bootstrap_setup_token(async_session)
    assert result.reason == "minted"


async def test_consume_setup_token_creates_first_admin(
    async_session: AsyncSession,
) -> None:
    bootstrap = await maybe_bootstrap_setup_token(async_session)
    assert bootstrap.plaintext is not None

    user = await consume_setup_token(
        async_session,
        plaintext=bootstrap.plaintext,
        username="root",
        password="goodpassword",
    )
    assert user.role == ROLE_ADMIN
    assert user.is_active is True
    assert user.hashed_password is not None  # bcrypt hash

    # Token row marked consumed.
    consumed = (
        await async_session.execute(select(SetupToken))
    ).scalar_one()
    assert consumed.consumed_at is not None


async def test_consume_setup_token_replay_rejected(
    async_session: AsyncSession,
) -> None:
    bootstrap = await maybe_bootstrap_setup_token(async_session)
    assert bootstrap.plaintext is not None

    await consume_setup_token(
        async_session,
        plaintext=bootstrap.plaintext,
        username="root",
        password="goodpassword",
    )

    with pytest.raises(SetupTokenAlreadyConsumedError):
        await consume_setup_token(
            async_session,
            plaintext=bootstrap.plaintext,
            username="root2",
            password="goodpassword",
        )


async def test_consume_setup_token_wrong_token_rejected(
    async_session: AsyncSession,
) -> None:
    await maybe_bootstrap_setup_token(async_session)
    with pytest.raises(SetupTokenInvalidError):
        await consume_setup_token(
            async_session,
            plaintext="not-the-real-token",
            username="root",
            password="goodpassword",
        )


async def test_consume_setup_token_expired_rejected(
    async_session: AsyncSession,
) -> None:
    """A past-expiry token must be rejected."""
    expired_plain = "abcdefghij" * 5  # 50 chars
    expired_row = SetupToken(
        token_hash=__import__("romarr.auth.hashing", fromlist=["hash_api_key"]).hash_api_key(
            expired_plain
        ),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    async_session.add(expired_row)
    await async_session.commit()

    with pytest.raises(SetupTokenExpiredError):
        await consume_setup_token(
            async_session,
            plaintext=expired_plain,
            username="root",
            password="goodpassword",
        )


async def test_consume_setup_token_after_first_admin_locked_out(
    async_session: AsyncSession,
) -> None:
    """FR-021: even with an unconsumed token, no new admin can be minted once one exists."""
    bootstrap = await maybe_bootstrap_setup_token(async_session)
    assert bootstrap.plaintext is not None

    # Manually create an active admin.
    async_session.add(
        User(username="alice", role=ROLE_ADMIN, hashed_password=hash_password("x"))
    )
    await async_session.commit()

    # Token still alive in the DB but cannot be used.
    with pytest.raises(SetupTokenAlreadyConsumedError):
        await consume_setup_token(
            async_session,
            plaintext=bootstrap.plaintext,
            username="root",
            password="goodpassword",
        )
