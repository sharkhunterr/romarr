"""Pydantic schemas for the importer feature (spec 008).

API surface only — the importer's persistence layer (``ImportHistory``,
``UnidentifiedDump`` extensions) is system-written, so there is no
``Create`` schema for the audit table; the operator-facing surfaces
are the manual-import / manual-match / retry / webhook endpoints.
The ``WebhookPayload`` discriminated union lands with the WATCH
slice once the per-client variants are needed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ImportHistoryRead(BaseModel):
    """Read shape for the ``GET /api/v3/rom/import/history`` endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_path: str
    dest_path: str | None
    download_client_id: int | None
    download_client_native_id: str | None
    game_id: int | None
    release_id: int | None
    dump_id: int | None
    source_hash_sha1: str | None
    confidence: float | None
    imported_via: Literal["automatic", "manual", "rss", "api", "webhook"]
    success: bool
    coalesced: bool
    warning: str | None
    error_msg: str | None
    imported_by: str | None
    correlation_id: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None


class ManualImportEntry(BaseModel):
    """One row in :class:`ManualImportRequest`. Identifies a file
    on disk plus the operator's chosen target Game / Release."""

    model_config = ConfigDict(extra="forbid")

    path: Path
    game_id: int
    release_id: int | None = None
    force: bool = False


class ManualImportRequest(BaseModel):
    """Bulk manual-import payload (POST
    ``/api/v3/rom/import/manual``)."""

    model_config = ConfigDict(extra="forbid")

    entries: Annotated[list[ManualImportEntry], Field(min_length=1)]


class ManualMatchRequest(BaseModel):
    """Match an existing ``unidentified_dump`` row to a Game (and
    optionally a Release) — POST
    ``/api/v3/rom/unidentified/{id}/match``."""

    model_config = ConfigDict(extra="forbid")

    game_id: int
    release_id: int | None = None


class RetryResponse(BaseModel):
    """Response to POST ``/api/v3/rom/import/retry/{import_id}``.
    Wraps the ``ImportHistoryRead`` produced by the retry."""

    history: ImportHistoryRead


class UnidentifiedDumpRead(BaseModel):
    """Extended read shape covering the spec 008 columns
    (``rejection_reason``, ``library_id``, ``suggested_game_id``)
    plus the foundation columns. Returned by GET
    ``/api/v3/rom/unidentified``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    size_bytes: int
    discovered_at: datetime
    crc32: str | None
    md5: str | None
    sha1: str | None
    attempt_count: int
    last_attempt_at: datetime | None
    last_error: str | None
    suggested_platform_id: int | None
    rejection_reason: str | None
    library_id: int | None
    suggested_game_id: int | None


__all__ = [
    "ImportHistoryRead",
    "ManualImportEntry",
    "ManualImportRequest",
    "ManualMatchRequest",
    "RetryResponse",
    "UnidentifiedDumpRead",
]
