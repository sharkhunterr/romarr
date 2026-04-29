"""Admin user-CRUD service.

Spec 010 FR-026 endpoints under ``/api/v3/user``:
  - GET    /api/v3/user                       — list
  - POST   /api/v3/user                       — create
  - GET    /api/v3/user/{id}                  — read
  - PUT    /api/v3/user/{id}                  — update (role / email / activate)
  - DELETE /api/v3/user/{id}                  — delete
  - POST   /api/v3/user/{id}/reset-password   — admin-mints a one-time
                                                reset token (FR per spec 010
                                                User Story 8)

Per the FR-021 / User Story 8 acceptance scenario "delete the lone
admin": the service refuses with ``cannot_delete_last_admin`` so the
operator can never lock themselves out.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from romarr.auth.constants import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
)
from romarr.auth.hashing import hash_password
from romarr.auth.models import SetupToken, User
from romarr.auth.sessions import revoke_all_for_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ALLOWED_ROLES: frozenset[str] = frozenset({ROLE_ADMIN, ROLE_USER, ROLE_READONLY})


class UserCreateError(ValueError):
    """User creation failed at validation. Carries a stable ``code``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CannotDeleteLastAdminError(ValueError):
    """Refuse to delete a user whose absence would leave zero admins."""

    code = "cannot_delete_last_admin"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def list_users(
    session: AsyncSession,
    *,
    include_system: bool = False,
) -> list[User]:
    """Return every user, optionally including the id=0 system sentinel."""
    stmt = select(User).order_by(User.id)
    if not include_system:
        stmt = stmt.where(User.id != 0)
    return list((await session.execute(stmt)).scalars().all())


async def get_user(session: AsyncSession, *, user_id: int) -> User | None:
    return (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password: str | None,
    role: str = ROLE_USER,
    email: str | None = None,
    is_active: bool = True,
) -> User:
    """Create a user.

    ``password`` may be ``None`` for OIDC-only users (an admin
    creates a placeholder row that the OIDC callback later fills in).
    """
    if not username or not username.strip():
        raise UserCreateError("validation_failed", "username must not be empty")
    if role not in _ALLOWED_ROLES:
        raise UserCreateError(
            "validation_failed", f"unknown role {role!r}; allowed: {sorted(_ALLOWED_ROLES)!r}"
        )

    user = User(
        username=username.strip(),
        email=email or None,
        hashed_password=hash_password(password) if password else None,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # Translate FK / UNIQUE failures to a stable code.
        msg = str(exc.orig) if exc.orig else str(exc)
        if "username" in msg.lower():
            raise UserCreateError("username_taken", "username already exists") from exc
        if "email" in msg.lower():
            raise UserCreateError("email_taken", "email already exists") from exc
        raise UserCreateError("validation_failed", msg) from exc

    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def update_user(
    session: AsyncSession,
    *,
    user_id: int,
    role: str | None = None,
    email: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Admin-side update of a user row.

    Username changes are NOT supported — they would invalidate any
    trusted-proxy header maps. Operators wanting to rename someone
    delete and re-create.
    """
    user = await get_user(session, user_id=user_id)
    if user is None:
        raise UserCreateError("not_found", f"user {user_id} not found")

    # Refuse to demote the lone admin (mirror the FR-021 last-admin
    # guarantee from delete).
    if role is not None and role != user.role:
        if role not in _ALLOWED_ROLES:
            raise UserCreateError(
                "validation_failed",
                f"unknown role {role!r}; allowed: {sorted(_ALLOWED_ROLES)!r}",
            )
        if (
            user.role == ROLE_ADMIN
            and role != ROLE_ADMIN
            and not await _has_other_admin(session, exclude_user_id=user.id)
        ):
            raise CannotDeleteLastAdminError(
                "cannot demote the lone admin"
            )
        user.role = role

    if email is not None:
        user.email = email or None

    if is_active is not None:
        # Deactivating a user revokes their sessions immediately —
        # FR-027 / Edge Case "user is deactivated while session live".
        if user.is_active and not is_active:
            await revoke_all_for_user(session, user_id=user.id)
        user.is_active = is_active

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        msg = str(exc.orig) if exc.orig else str(exc)
        if "email" in msg.lower():
            raise UserCreateError("email_taken", "email already exists") from exc
        raise UserCreateError("validation_failed", msg) from exc
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def delete_user(session: AsyncSession, *, user_id: int) -> bool:
    """Delete a user; refuses to delete the lone admin (User Story 8.3).

    Returns ``True`` when a row was deleted; ``False`` when the user
    didn't exist (idempotent miss).
    """
    user = await get_user(session, user_id=user_id)
    if user is None:
        return False
    if user.id == 0:
        # The system sentinel must not be removable — every spec's
        # ``*_by`` FK depends on it.
        raise CannotDeleteLastAdminError("cannot delete the system sentinel")

    if user.role == ROLE_ADMIN and not await _has_other_admin(
        session, exclude_user_id=user.id
    ):
        raise CannotDeleteLastAdminError("cannot delete the lone admin")

    await session.delete(user)
    await session.commit()
    return True


# ---------------------------------------------------------------------------
# Admin-mints reset token
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreatedResetToken:
    """Returned ONCE from :func:`create_password_reset_token`."""

    plaintext: str
    expires_at: datetime


async def create_password_reset_token(
    session: AsyncSession, *, user_id: int, ttl_minutes: int = 60
) -> CreatedResetToken:
    """Mint a one-time reset token an admin shares out-of-band.

    Per User Story 8.2 — SMTP is out of scope at MVP, so the API
    response carries the plaintext; the admin pastes it into a chat
    or wiki.
    """
    user = await get_user(session, user_id=user_id)
    if user is None:
        raise UserCreateError("not_found", f"user {user_id} not found")

    plaintext = secrets.token_urlsafe(32)
    from romarr.auth.hashing import hash_api_key

    row = SetupToken(
        token_hash=hash_api_key(plaintext),
        expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    )
    # We piggyback on the SetupToken table for one-shot tokens — the
    # DB doesn't differentiate "setup" tokens from "reset" tokens
    # because both are short-lived, single-consume secrets. A future
    # spec may split these if they diverge in shape.
    session.add(row)
    await session.commit()
    return CreatedResetToken(plaintext=plaintext, expires_at=row.expires_at)


# ---------------------------------------------------------------------------
# Trusted-proxy auto-create (FR-018)
# ---------------------------------------------------------------------------


async def get_or_auto_create_proxy_user(
    session: AsyncSession,
    *,
    username: str,
    default_role: str = ROLE_USER,
) -> User:
    """Return the user matching ``username`` or auto-create at first contact.

    Spec 010 FR-018 (clarified): a trusted-proxy username that does
    not match any existing user MUST be auto-created with the
    configurable default role (``user`` by default). The OIDC subject
    fields stay NULL — the proxy is the source of truth.
    """
    if not username or not username.strip():
        raise UserCreateError("validation_failed", "username must not be empty")
    if default_role not in _ALLOWED_ROLES:
        raise UserCreateError(
            "validation_failed",
            f"unknown role {default_role!r}; allowed: {sorted(_ALLOWED_ROLES)!r}",
        )

    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        username=username.strip(),
        role=default_role,
        is_active=True,
        hashed_password=None,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _has_other_admin(
    session: AsyncSession, *, exclude_user_id: int
) -> bool:
    """``True`` when at least one OTHER active admin exists.

    "Other" means: not ``exclude_user_id``, ``id != 0`` (system
    sentinel), and ``is_active = True``.
    """
    result = await session.execute(
        select(User.id)
        .where(
            User.id != exclude_user_id,
            User.id != 0,
            User.role == ROLE_ADMIN,
            User.is_active.is_(True),
        )
        .limit(1)
    )
    return result.first() is not None
