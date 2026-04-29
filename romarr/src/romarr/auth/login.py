"""Forms-login service — FR-010 / FR-002 (RBAC).

The service validates ``(username, password)`` against the persisted
bcrypt hash via constant-time compare. It returns the matched ``User``
on success and raises a structured error otherwise.

Spec 010 FR-010a (per-IP rate limit) lives in :mod:`romarr.auth.rate_limit`
— this service assumes the limit was checked upstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.auth.errors import InvalidCredentialsError, UserDeactivatedError
from romarr.auth.hashing import verify_password
from romarr.auth.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def authenticate(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> User:
    """Validate credentials. Returns the User on success.

    Raises :class:`InvalidCredentialsError` on missing user, missing
    password hash, or wrong password — same exception class for all
    three so the upstream API layer's generic 401 message is honest.
    Raises :class:`UserDeactivatedError` when the user is found but
    ``is_active = False`` (avoids the no-such-user vs. deactivated
    timing oracle).
    """
    if not username or not password:
        raise InvalidCredentialsError("username and password are required")

    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()

    if user is None:
        # Do a wasted bcrypt check anyway so the timing of the
        # "no such user" path matches the "wrong password" path.
        verify_password(password, "$2b$12$" + "0" * 53)
        raise InvalidCredentialsError("invalid credentials")

    if user.hashed_password is None:
        # OIDC-only user — no password to verify against.
        raise InvalidCredentialsError("user has no password set")

    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("invalid credentials")

    if not user.is_active:
        raise UserDeactivatedError("user is deactivated")

    return user
