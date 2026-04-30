"""Pydantic schemas for the search subsystem's HTTP layer.

Persistence triplets (``*Read`` / ``*Create`` / ``*Update``) where
each makes sense — :class:`SearchHistory` is system-written (no
Create / Update on the API surface), :class:`SearchCache` is
debug-only (no Create / Update at all), :class:`Blocklist` is
append-only (no Update — modification = delete + re-create).

Plus the request shapes for the manual / grab / Sonarr-compat
``command`` endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Blocklist
# ---------------------------------------------------------------------------


class BlocklistRead(_Base):
    id: int
    indexer_id: int | None
    indexer_guid: str | None
    release_title: str
    hash_sha1: str | None
    hash_crc32: str | None
    reason: str
    added_by: str
    added_at: datetime


class BlocklistCreate(_Base):
    """At least one of (indexer_id+indexer_guid) / hash_sha1 / hash_crc32
    MUST be populated — an entry that matches nothing is meaningless
    (FR-021)."""

    indexer_id: int | None = None
    indexer_guid: Annotated[str | None, Field(default=None, max_length=255)] = None
    release_title: Annotated[str, Field(min_length=1, max_length=512)]
    hash_sha1: Annotated[str | None, Field(default=None, min_length=40, max_length=40)] = None
    hash_crc32: Annotated[str | None, Field(default=None, min_length=8, max_length=8)] = None
    reason: Annotated[str, Field(min_length=1, max_length=255)]
    added_by: Annotated[str, Field(default="system", max_length=64)] = "system"

    @model_validator(mode="after")
    def _at_least_one_match_field(self) -> Self:
        has_guid = self.indexer_id is not None and self.indexer_guid is not None
        if not has_guid and not self.hash_sha1 and not self.hash_crc32:
            raise ValueError(
                "blocklist entry must carry one of "
                "(indexer_id+indexer_guid), hash_sha1, or hash_crc32 — "
                "an empty entry matches nothing"
            )
        return self


# ---------------------------------------------------------------------------
# Search history (read-only on the API surface)
# ---------------------------------------------------------------------------


class SearchHistoryRead(_Base):
    id: int
    search_type: str
    query: str | None
    indexer_id: int | None
    game_id: int | None
    release_id: int | None
    results_count: int
    grabbed_release_id: int | None
    chosen_indexer_guid: str | None
    score: int | None
    no_grab_reason: str | None
    score_breakdown: list[dict[str, Any]] | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    correlation_id: str


# ---------------------------------------------------------------------------
# Search cache (debug-only on the API surface)
# ---------------------------------------------------------------------------


class SearchCacheRead(_Base):
    id: int
    indexer_id: int
    cache_key: str
    query: str
    category_ids: list[int]
    fetched_at: datetime
    expires_at: datetime
    last_read_at: datetime
    # response_xml + parsed_results intentionally omitted from the
    # API surface — they're large blobs only useful via the
    # operator-tooling spec's replay path.


# ---------------------------------------------------------------------------
# Manual / grab / command request shapes
# ---------------------------------------------------------------------------


class ManualSearchRequest(_Base):
    """POST /api/v3/rom/search/manual."""

    query: Annotated[str, Field(min_length=1, max_length=512)]
    indexer_ids: list[int] | None = None
    """When None, every enabled indexer is queried."""
    platform_id: int | None = None
    strict: bool = False
    """When true, candidates that would auto-reject are dropped from
    the response. When false (default), they're returned with
    ``would_auto_reject=true`` so the operator can decide."""


class GrabRequest(_Base):
    """POST /api/v3/rom/release/grab.

    Operator picks an exact result from a manual search. ``force``
    overrides the blocklist gate (FR-022 / SC-006); the pipeline's
    profile gates still apply.
    """

    indexer_id: int
    indexer_guid: Annotated[str, Field(min_length=1, max_length=255)]
    download_url: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1, max_length=512)]
    release_id: int | None = None


_CommandName = Literal[
    "MissingSearch",
    "CutoffSearch",
    "RssSync",
    "IndexerSearch",
]


class CommandRequest(_Base):
    """POST /api/v3/command — Sonarr-compat shape.

    Notifiarr / Recyclarr-style tools use this payload to trigger
    background search rounds.
    """

    name: _CommandName
    indexer_ids: list[int] | None = None
    limit: Annotated[int | None, Field(default=None, ge=1, le=500)] = None


__all__ = [
    "BlocklistCreate",
    "BlocklistRead",
    "CommandRequest",
    "GrabRequest",
    "ManualSearchRequest",
    "SearchCacheRead",
    "SearchHistoryRead",
]
