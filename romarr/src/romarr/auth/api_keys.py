"""API-key service — FR-005 / FR-006 / FR-007 / FR-008 / FR-009 / FR-009a.

Behaviour:
  - :func:`create_api_key` mints a fresh plaintext + persists the
    BLAKE2b digest. The plaintext is returned exactly once (FR-005);
    the caller is responsible for showing it once and never again.
  - :func:`resolve_api_key` looks up a key by plaintext and returns
    the owning user. Raises :class:`ApiKeyInvalidError` /
    :class:`ApiKeyExpiredError` / :class:`ApiKeyRevokedError` so the
    upstream chain can map them to a 401.
  - :func:`revoke_api_key` DELETEs the row by id. The next request
    bearing that key fails (FR-007).

Scope validation lives in :mod:`romarr.auth.permissions` — this
service just persists what the caller supplies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from romarr.auth.constants import SCOPE_ADMIN, SCOPE_READ, SCOPE_WRITE
from romarr.auth.errors import (
    ApiKeyExpiredError,
    ApiKeyInvalidError,
)
from romarr.auth.hashing import generate_api_key, hash_api_key
from romarr.auth.models import ApiKey, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ALLOWED_SCOPES: frozenset[str] = frozenset({SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN})


@dataclass(frozen=True, slots=True)
class CreatedApiKey:
    """Result of :func:`create_api_key`.

    ``plaintext`` is the only place the operator can read the key —
    once this object is dropped, the plaintext is gone forever.
    """

    api_key_id: int
    plaintext: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None


async def create_api_key(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
) -> CreatedApiKey:
    """Mint a fresh API key for ``user`` and persist its hash.

    ``scopes`` defaults to ``["read"]``. Each scope MUST be one of
    ``{"read", "write", "admin"}`` (FR-009a). Empty scope lists are
    rejected (FR-009 — Edge Case "scopes_required").
    """
    if user.id is None:
        raise ValueError("user must be persisted before creating an api key")
    if not name or not name.strip():
        raise ValueError("api key name must not be empty")

    requested_scopes = scopes if scopes is not None else [SCOPE_READ]
    if not requested_scopes:
        raise ValueError("scopes_required")
    invalid = [s for s in requested_scopes if s not in _ALLOWED_SCOPES]
    if invalid:
        raise ValueError(
            f"unknown scope(s) {invalid!r}; allowed: {sorted(_ALLOWED_SCOPES)!r}"
        )

    plaintext, key_hash, key_prefix = generate_api_key()
    row = ApiKey(
        user_id=user.id,
        name=name.strip(),
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=list(dict.fromkeys(requested_scopes)),  # dedup, preserve order
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return CreatedApiKey(
        api_key_id=row.id,
        plaintext=plaintext,
        key_prefix=key_prefix,
        scopes=row.scopes,
        expires_at=row.expires_at,
    )


@dataclass(frozen=True, slots=True)
class ResolvedApiKey:
    """The matched user + the API key's authoritative scope list."""

    user: User
    scopes: list[str]
    api_key_id: int


async def resolve_api_key(
    session: AsyncSession,
    *,
    plaintext: str,
) -> ResolvedApiKey:
    """Validate ``plaintext`` and return the bound user + scopes.

    Best-effort updates ``last_used_at`` / ``last_used_ip`` are NOT
    done here — the caller (the auth chain) is best positioned to
    pass the IP and to schedule the update non-blockingly per FR-027.
    """
    if not plaintext:
        raise ApiKeyInvalidError("empty api key")

    candidate_hash = hash_api_key(plaintext)
    row = (
        await session.execute(select(ApiKey).where(ApiKey.key_hash == candidate_hash))
    ).scalar_one_or_none()
    if row is None:
        raise ApiKeyInvalidError("api key did not match")

    if row.expires_at is not None:
        # SQLite drops tzinfo on read; coerce back to UTC-aware.
        expires_at = (
            row.expires_at
            if row.expires_at.tzinfo is not None
            else row.expires_at.replace(tzinfo=UTC)
        )
        if expires_at < datetime.now(UTC):
            raise ApiKeyExpiredError("api key expired")

    user = (
        await session.execute(select(User).where(User.id == row.user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise ApiKeyInvalidError("api key owner deactivated or removed")

    return ResolvedApiKey(user=user, scopes=list(row.scopes), api_key_id=row.id)


async def touch_api_key(
    session: AsyncSession,
    *,
    api_key_id: int,
    ip_address: str | None,
) -> None:
    """Best-effort ``last_used_at`` / ``last_used_ip`` update (FR-027).

    Failures here MUST NOT propagate — the request has already been
    authenticated; auditing is observability, not correctness.
    """
    try:
        row = (
            await session.execute(
                select(ApiKey).where(ApiKey.id == api_key_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.last_used_at = datetime.now(UTC)
        row.last_used_ip = ip_address
        await session.commit()
    except Exception:
        await session.rollback()


async def revoke_api_key(
    session: AsyncSession,
    *,
    api_key_id: int,
) -> bool:
    """Delete an API key row by id. Returns ``True`` when one was removed."""
    result = await session.execute(delete(ApiKey).where(ApiKey.id == api_key_id))
    await session.commit()
    # ``Result.rowcount`` lives on DML CursorResults; look it up
    # dynamically so mypy doesn't choke on the looser ``Result`` type.
    rowcount = getattr(result, "rowcount", 0) or 0
    return int(rowcount) > 0


async def list_api_keys_for_user(
    session: AsyncSession,
    *,
    user_id: int,
) -> list[ApiKey]:
    """Return every API key row for a user. Plaintext is never resurrected."""
    rows = (
        await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.id)
        )
    ).scalars().all()
    return list(rows)
