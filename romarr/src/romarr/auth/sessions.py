"""Session service — sliding 30-day TTL per FR-012a.

Behaviour:
  - :func:`create_session` — mints a 32-byte URL-safe random session
    id, persists a row with ``last_used_at = now`` and
    ``expires_at = now + 30 days``, returns the plaintext id (the
    cookie value).
  - :func:`resolve_session` — looks up an active session by id;
    raises :class:`SessionNotFoundError` / :class:`SessionExpiredError`
    when the row is missing or past expiry. On hit, slides the
    expiry forward by another 30 days (best-effort, non-blocking
    semantics modelled by ``commit=False`` callers).
  - :func:`revoke_session` — DELETEs the row; idempotent.

Per FR-012a the cookie's ``Max-Age`` mirrors ``expires_at - now`` so
the browser drops it at the same moment the server does. Computing
``Max-Age`` is the responsibility of the API layer.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from romarr.auth.errors import SessionExpiredError, SessionNotFoundError
from romarr.auth.models import Session as SessionRow
from romarr.auth.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession as SqlSession

SESSION_TTL_DAYS: int = 30
"""FR-012a sliding window."""

SESSION_ID_BYTES: int = 32
"""Random bytes encoded into the session cookie value (URL-safe)."""


def _ensure_utc(value: datetime) -> datetime:
    """Coerce a naive datetime to UTC-aware.

    SQLite + aiosqlite stores ``DateTime(timezone=True)`` columns as
    ISO strings without timezone info; on read they come back naive.
    Re-attaching UTC is safe because we only ever WRITE UTC values
    in the auth layer.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class CreatedSession:
    """Tuple-shaped result of :func:`create_session`.

    ``session_id`` is the plaintext cookie value (URL-safe random).
    ``expires_at`` is timezone-aware UTC.
    """

    session_id: str
    expires_at: datetime


async def create_session(
    session: SqlSession,
    *,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> CreatedSession:
    """Create a new session row for ``user`` and return its plaintext id."""
    if user.id is None:
        raise ValueError("user must be persisted before creating a session")

    now = datetime.now(UTC)
    sid = secrets.token_urlsafe(SESSION_ID_BYTES)
    row = SessionRow(
        id=sid,
        user_id=user.id,
        last_used_at=now,
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        user_agent=user_agent,
        ip_address=ip_address,
        created_at=now,
    )
    session.add(row)
    await session.commit()
    return CreatedSession(session_id=sid, expires_at=row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at)


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    """The session row + its bound user, returned from :func:`resolve_session`."""

    user: User
    expires_at: datetime


async def resolve_session(
    session: SqlSession,
    *,
    session_id: str,
    slide: bool = True,
) -> ResolvedSession:
    """Look up a session by its plaintext id and slide the TTL forward.

    Raises:
      :class:`SessionNotFoundError` — no row matches.
      :class:`SessionExpiredError` — row matches but ``expires_at`` has
        already passed.

    Setting ``slide=False`` skips the sliding-TTL update — used by
    diagnostic tooling that wants to inspect a session without
    extending its life.
    """
    if not session_id:
        raise SessionNotFoundError("empty session id")

    row = (
        await session.execute(
            select(SessionRow).where(SessionRow.id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise SessionNotFoundError("no such session")

    now = datetime.now(UTC)
    expires_at = _ensure_utc(row.expires_at)
    if expires_at < now:
        # Session expired — clean it up so future calls are O(1)
        # missing rather than O(1) explicit-expired.
        await session.delete(row)
        await session.commit()
        raise SessionExpiredError("session expired")

    user = (
        await session.execute(select(User).where(User.id == row.user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        # User disappeared / deactivated while session was alive.
        await session.delete(row)
        await session.commit()
        raise SessionExpiredError("user deactivated or removed")

    if slide:
        row.last_used_at = now
        row.expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        await session.commit()
        await session.refresh(row)
        expires_at = _ensure_utc(row.expires_at)

    return ResolvedSession(user=user, expires_at=expires_at)


async def revoke_session(
    session: SqlSession,
    *,
    session_id: str,
) -> bool:
    """Delete the session row. Idempotent; ``True`` when a row was deleted."""
    result = await session.execute(
        delete(SessionRow).where(SessionRow.id == session_id)
    )
    await session.commit()
    # ``Result.rowcount`` is only present on DML CursorResults; mypy
    # types ``Result`` more loosely so we look it up dynamically.
    rowcount = getattr(result, "rowcount", 0) or 0
    return int(rowcount) > 0


async def revoke_all_for_user(
    session: SqlSession,
    *,
    user_id: int,
) -> int:
    """Revoke every session for a user (e.g., on password change). Returns count."""
    result = await session.execute(
        delete(SessionRow).where(SessionRow.user_id == user_id)
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
