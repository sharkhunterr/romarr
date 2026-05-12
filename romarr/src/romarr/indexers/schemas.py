"""Pydantic schemas for the indexer feature's HTTP layer.

Each entity has the standard ``*Read / *Create / *Update`` triplet.
``IndexerRead`` deliberately omits ``api_key_encrypted`` and exposes
``is_configured: bool`` (FR-022 — encrypted blob never leaks in
responses). ``ApplicationRead`` never carries the plaintext app token
either; the plaintext is returned exactly once from the POST handler
in :class:`ApplicationCreateResult`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


class IndexerRead(_Base):
    id: int
    name: str
    implementation: str
    url: str
    is_configured: bool
    categories: list[int]
    priority: int
    # Slice 432 — master enable/disable. When False, the indexer
    # is hidden from every search round / RSS poll / grab dispatch
    # regardless of the per-capability flags below.
    enabled: bool
    enable_rss: bool
    enable_automatic_search: bool
    enable_interactive_search: bool
    tags: list[int] | None
    rate_limit_seconds: int
    min_seeders: int
    download_client_id: int | None
    source: str
    prowlarr_app_id: int | None
    seed_ratio: float | None
    seed_time_minutes: int | None
    discount_only: bool
    priority_indexer: bool
    timeout_seconds: int
    result_limit: int
    last_health_at: datetime | None
    last_health_ok: bool | None
    last_health_error: str | None


class IndexerCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    # ``'grabarr'`` accepted at the API layer so the (future) "Add
    # Grabarr" wizard can POST through the same /api/v3/indexer
    # endpoint. The DB CHECK was widened in migration 0022; the
    # Add Indexer modal's ``_IMPLEMENTATIONS`` array still only
    # surfaces newznab/torznab today.
    implementation: Literal["newznab", "torznab", "grabarr"]
    url: Annotated[str, Field(min_length=1)]
    api_key: Annotated[str | None, Field(default=None, max_length=255)] = None
    categories: list[int] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=1, le=100)] = 25
    enabled: bool = True
    enable_rss: bool = True
    enable_automatic_search: bool = True
    enable_interactive_search: bool = True
    tags: list[int] | None = None
    rate_limit_seconds: Annotated[int, Field(ge=0, le=600)] = 5
    min_seeders: Annotated[int, Field(ge=0)] = 1
    download_client_id: int | None = None
    source: Literal["manual", "prowlarr"] = "manual"
    prowlarr_app_id: int | None = None
    seed_ratio: float | None = Field(default=None, ge=0, le=99.99)
    seed_time_minutes: Annotated[int | None, Field(default=None, ge=0)] = None
    discount_only: bool = False
    priority_indexer: bool = False
    timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 30
    result_limit: Annotated[int, Field(ge=1, le=500)] = 100


class IndexerUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    implementation: Literal["newznab", "torznab", "grabarr"] | None = None
    url: Annotated[str | None, Field(default=None, min_length=1)] = None
    api_key: Annotated[str | None, Field(default=None, max_length=255)] = None
    categories: list[int] | None = None
    priority: Annotated[int | None, Field(default=None, ge=1, le=100)] = None
    enabled: bool | None = None
    enable_rss: bool | None = None
    enable_automatic_search: bool | None = None
    enable_interactive_search: bool | None = None
    tags: list[int] | None = None
    rate_limit_seconds: Annotated[int | None, Field(default=None, ge=0, le=600)] = None
    min_seeders: Annotated[int | None, Field(default=None, ge=0)] = None
    download_client_id: int | None = None
    seed_ratio: float | None = Field(default=None, ge=0, le=99.99)
    seed_time_minutes: Annotated[int | None, Field(default=None, ge=0)] = None
    discount_only: bool | None = None
    priority_indexer: bool | None = None
    timeout_seconds: Annotated[int | None, Field(default=None, ge=5, le=600)] = None
    result_limit: Annotated[int | None, Field(default=None, ge=1, le=500)] = None


class IndexerSchemaEntry(_Base):
    """One entry in ``GET /api/v3/indexer/schema``.

    Prowlarr expects a list of indexer "implementations" Romarr supports
    so it can build its UI for adding a new indexer. We support
    Newznab and Torznab.
    """

    implementation: str
    implementation_name: str
    config_contract: str
    fields: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ApplicationRead(_Base):
    id: int
    name: str
    sync_level: str
    prowlarr_url: str
    enabled: bool
    created_at: datetime
    last_sync_at: datetime | None


class ApplicationCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    sync_level: Literal["disabled", "add_only", "full_sync"] = "full_sync"
    prowlarr_url: Annotated[str, Field(min_length=1)]
    prowlarr_api_key: Annotated[str, Field(min_length=1, max_length=255)]


class ApplicationCreateResult(ApplicationRead):
    """Returned by POST /api/v3/applications.

    Carries the ``app_token`` plaintext exactly once; subsequent reads
    return :class:`ApplicationRead` (no token).
    """

    app_token: str


__all__ = [
    "ApplicationCreate",
    "ApplicationCreateResult",
    "ApplicationRead",
    "IndexerCreate",
    "IndexerRead",
    "IndexerSchemaEntry",
    "IndexerUpdate",
]
