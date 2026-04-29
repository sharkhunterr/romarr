"""SQLAlchemy ORM models for spec 010 — Auth & Multi-User.

Four tables:
  - ``user``         — identity + role + preferences
  - ``session``      — server-side session record with sliding TTL
  - ``api_key``      — hashed API keys with coarse 3-tier scopes
  - ``setup_token``  — bootstrap token (one-shot, FR-019/020/021)

Per the clarified FR-001/FR-002/FR-003 (Q5 — drop is_superuser): the
schema MUST NOT carry an ``is_superuser`` column. ``role`` is the
single source of truth; ``User.is_superuser`` is a derived
read-only property.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from romarr.auth.constants import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
)
from romarr.domain.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Authenticated user.

    Per FR-001 (clarified): ``role`` is the only role-storage column.
    The ``is_superuser`` Python property below is derived; it is
    never persisted, never UPDATE-able.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    username: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    hashed_password: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ROLE_USER
    )

    oidc_subject: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    oidc_provider: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "oidc_provider", "oidc_subject", name="uq_user_oidc_identity"
        ),
        CheckConstraint(
            f"role IN ('{ROLE_ADMIN}', '{ROLE_USER}', '{ROLE_READONLY}')",
            name="ck_user_role",
        ),
    )

    @property
    def is_superuser(self) -> bool:
        """Read-only convenience for fastapi-users-style code paths.

        Per the clarified FR-002: this is a Python property, NOT a
        column. Mutating it is forbidden (no setter); to change a
        user's privilege, update ``role``.
        """
        return self.role == ROLE_ADMIN


class Session(Base):
    """Server-side session record with sliding 30-day TTL (FR-012a).

    The cookie carries ``id`` only; the session row holds everything
    else. ``last_used_at`` updates on every authenticated request;
    ``expires_at = last_used_at + 30 days`` is recomputed in the same
    write so the cookie's ``Max-Age`` can mirror it.
    """

    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class ApiKey(Base, TimestampMixin):
    """Revocable API key with coarse 3-tier scopes (FR-005 / FR-009a).

    Plaintext is exposed exactly once at creation; we only ever
    persist the BLAKE2b digest and a short prefix for UI display.
    """

    __tablename__ = "api_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    # Subset of {"read", "write", "admin"} — validated at the service
    # layer (the DB stores plain JSON for portability between SQLite
    # and PostgreSQL).
    scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["read"]
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")


class SetupToken(Base, TimestampMixin):
    """One-shot bootstrap token used for first-admin creation.

    Per FR-019/020/021: generated on startup when the user table is
    empty; valid for 24 hours; consumed exactly once. The token's
    plaintext appears once in the application logs and is never
    persisted — we store only its BLAKE2b hash.

    A single-row table is sufficient because the system generates at
    most one valid setup token at any time (FR-021: no new token is
    minted after the first successful setup).
    """

    __tablename__ = "setup_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
