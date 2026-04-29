"""Pydantic-settings driven application configuration.

All env vars are prefixed ``ROMARR_``. Optional bearer tokens for
hash-match endpoints are populated only when set; an empty value
means "use anonymous public access" (spec 001 FR-026a).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Read once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="ROMARR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./romarr.db",
        description="SQLAlchemy connection URL. Defaults to SQLite for "
        "out-of-the-box single-binary usage; PostgreSQL is supported "
        "without code changes.",
    )

    # Hashing
    hash_buffer_bytes: int = Field(
        default=1 << 20,
        ge=4096,
        le=1 << 24,
        description="Streaming hash buffer size. 1 MiB default; tunable "
        "between 4 KiB and 16 MiB.",
    )

    # Hash-match cascade endpoints (spec 001 FR-026a)
    hasheous_base_url: str = Field(
        default="https://api.hasheous.org",
        description="Hasheous remote API base URL.",
    )
    hasheous_token: str = Field(
        default="",
        description="Optional bearer token for authenticated Hasheous "
        "access. Empty = anonymous public endpoint.",
    )
    playmatch_base_url: str = Field(
        default="https://api.playmatch.org",
        description="PlayMatch remote API base URL.",
    )
    playmatch_token: str = Field(
        default="",
        description="Optional bearer token for authenticated PlayMatch "
        "access. Empty = anonymous public endpoint.",
    )

    # Auth secret
    auth_secret_key: str = Field(
        default="",
        description="Master key used to derive Fernet encryption keys "
        "for credentials at rest. MUST be set in production.",
    )

    # Cover storage
    data_dir: str = Field(
        default="./data",
        description="Root data directory for covers, backups, and runtime files.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    Cached so settings are read once. Tests that need to override
    values should call ``get_settings.cache_clear()`` after mutating
    environment variables.
    """
    return Settings()
