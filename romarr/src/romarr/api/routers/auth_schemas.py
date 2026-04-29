"""Pydantic request/response models for the auth endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from romarr.auth.constants import SCOPE_READ


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


class SetupRequest(_Base):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=8, max_length=255)]


class UserPublic(_Base):
    """Public-facing User shape — never carries hashed_password."""

    id: int
    username: str
    email: str | None = None
    role: str
    is_active: bool
    preferences: dict[str, Any] = Field(default_factory=dict)
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SetupResponse(_Base):
    user: UserPublic


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


class LoginRequest(_Base):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=1, max_length=255)]


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


class UpdateMeRequest(_Base):
    """Self-service password / email / preferences update.

    All fields optional — clients send only what they want to change.
    Username changes are NOT supported here; admins do that via the
    user-CRUD endpoints (next slice).
    """

    password: Annotated[str | None, Field(min_length=8, max_length=255)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    preferences: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    scopes: list[str] = Field(default_factory=lambda: [SCOPE_READ])
    expires_at: datetime | None = None


class CreatedApiKeyResponse(_Base):
    """Returned ONCE at create-time. Carries the plaintext key."""

    id: int
    name: str
    plaintext: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None = None
    created_at: datetime


class ApiKeyPublic(_Base):
    """Read-side shape — plaintext is never resurrected."""

    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    created_at: datetime
    updated_at: datetime
