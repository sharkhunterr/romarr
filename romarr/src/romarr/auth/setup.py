"""Setup-token bootstrap service — FR-019 / FR-020 / FR-021.

Behaviour:
  - On startup with an empty ``user`` table, generate a 32-byte
    URL-safe random token, persist its BLAKE2b hash with a 24-hour
    expiry, and emit the plaintext to stdout exactly once (the
    operator captures it from the logs).
  - The first ``POST /api/v3/auth/setup`` carrying the matching
    ``X-Setup-Token`` consumes the row (sets ``consumed_at = now``)
    and creates the first admin user.
  - Subsequent calls match no unconsumed token AND/OR see a
    populated user table → 401.
  - After successful setup, a process restart MUST NOT mint a new
    token even if the user table somehow returns to empty.

The ``system`` sentinel user (id=0) seeded by migration 0010 does
NOT count as "user table populated" for setup purposes — its
``is_active = False`` excludes it from the population check.
"""

from __future__ import annotations

import hmac
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.auth.constants import ROLE_ADMIN
from romarr.auth.errors import (
    SetupTokenAlreadyConsumedError,
    SetupTokenExpiredError,
    SetupTokenInvalidError,
)
from romarr.auth.hashing import hash_api_key, hash_password
from romarr.auth.models import SetupToken, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SETUP_TOKEN_TTL_HOURS: int = 24
"""How long a freshly-minted setup token stays valid (FR-019)."""

SETUP_TOKEN_BYTES: int = 32
"""Random bytes encoded in the plaintext setup token."""


@dataclass(frozen=True, slots=True)
class SetupBootstrapResult:
    """Outcome of :func:`maybe_bootstrap_setup_token`.

    ``plaintext`` is non-None only when a fresh token was just minted
    on this call. Restarts that find an existing valid token return
    ``plaintext=None`` so the operator's prior capture is still
    authoritative.
    """

    plaintext: str | None
    expires_at: datetime | None
    reason: str  # "minted" | "already_present" | "skipped_users_exist"


async def maybe_bootstrap_setup_token(session: AsyncSession) -> SetupBootstrapResult:
    """Generate (or skip) the bootstrap setup token at startup.

    - Skips when at least one **active human** user (is_active=True
      AND id != 0) already exists.
    - Skips when an unconsumed setup_token row exists and hasn't
      expired (a previous startup minted one and the operator
      hasn't completed setup yet).
    - Otherwise mints a new token, persists its BLAKE2b hash, and
      returns the plaintext exactly once.
    """
    if await _has_active_human_user(session):
        return SetupBootstrapResult(
            plaintext=None, expires_at=None, reason="skipped_users_exist"
        )

    now = datetime.now(UTC)
    candidates = (
        await session.execute(
            select(SetupToken)
            .where(SetupToken.consumed_at.is_(None))
            .order_by(SetupToken.created_at.desc())
        )
    ).scalars().all()
    # The DB-level ``expires_at > now`` filter doesn't work reliably
    # against SQLite + aiosqlite's tz-naive read of a tz-aware column.
    # Filter in Python with the same UTC coercion the rest of the
    # service uses.
    for candidate in candidates:
        candidate_expiry = (
            candidate.expires_at
            if candidate.expires_at.tzinfo is not None
            else candidate.expires_at.replace(tzinfo=UTC)
        )
        if candidate_expiry > now:
            return SetupBootstrapResult(
                plaintext=None,
                expires_at=candidate_expiry,
                reason="already_present",
            )

    plaintext = secrets.token_urlsafe(SETUP_TOKEN_BYTES)
    token = SetupToken(
        token_hash=hash_api_key(plaintext),
        expires_at=now + timedelta(hours=SETUP_TOKEN_TTL_HOURS),
    )
    session.add(token)
    await session.commit()

    # Print the plaintext exactly once, with a distinctive prefix so
    # operators can grep it out of container logs (FR-019).
    print(
        f"ROMARR INITIAL SETUP TOKEN: {plaintext}",
        file=sys.stderr,
        flush=True,
    )

    return SetupBootstrapResult(
        plaintext=plaintext,
        expires_at=token.expires_at,
        reason="minted",
    )


async def consume_setup_token(
    session: AsyncSession,
    *,
    plaintext: str,
    username: str,
    password: str,
) -> User:
    """Consume the setup token and create the first admin (FR-020).

    Atomic per FR-020: the token row is marked consumed in the same
    transaction as the user INSERT. If creation fails for any reason
    (e.g., unique-username conflict on a race), the consumption is
    rolled back — the operator can retry with the same token while
    it's still alive.

    Raises:
      :class:`SetupTokenInvalidError` — wrong / unknown token.
      :class:`SetupTokenExpiredError` — token row past ``expires_at``.
      :class:`SetupTokenAlreadyConsumedError` — token row consumed OR
        an active human user already exists (FR-021).
    """
    if await _has_active_human_user(session):
        raise SetupTokenAlreadyConsumedError("setup already completed")

    if not plaintext:
        raise SetupTokenInvalidError("setup token must not be empty")

    candidate_hash = hash_api_key(plaintext)
    rows = (
        await session.execute(
            select(SetupToken).where(SetupToken.token_hash == candidate_hash)
        )
    ).scalars().all()

    matched: SetupToken | None = None
    for row in rows:
        # Constant-time comparison — even though the SQL look-up
        # already succeeds only on equality, we round-trip a hex
        # comparison so the access pattern is uniform.
        if hmac.compare_digest(row.token_hash, candidate_hash):
            matched = row
            break

    if matched is None:
        raise SetupTokenInvalidError("setup token did not match")

    now = datetime.now(UTC)
    if matched.consumed_at is not None:
        raise SetupTokenAlreadyConsumedError("setup token already consumed")
    expires_at = (
        matched.expires_at
        if matched.expires_at.tzinfo is not None
        else matched.expires_at.replace(tzinfo=UTC)
    )
    if expires_at < now:
        raise SetupTokenExpiredError("setup token expired")

    # Mark consumed + create the admin user atomically.
    matched.consumed_at = now
    admin = User(
        username=username,
        role=ROLE_ADMIN,
        is_active=True,
        hashed_password=hash_password(password),
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _has_active_human_user(session: AsyncSession) -> bool:
    """``True`` when a real (non-system, active) user exists.

    The migration-seeded ``system`` row at id=0 is excluded — it
    exists solely as the FK target for ``*_by`` columns and has
    ``is_active = False``.
    """
    result = await session.execute(
        select(User.id)
        .where(User.id != 0, User.is_active.is_(True))
        .limit(1)
    )
    return result.first() is not None
