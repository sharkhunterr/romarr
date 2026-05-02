"""Pagination + error envelope shapes (T004, FR-007 / FR-010).

Every list endpoint in the project surfaces the canonical
``PaginationEnvelope``; every error response surfaces the
canonical ``ErrorEnvelope``. The shapes are documented at
``/api/v3/notification/webhook-payloads.md`` as part of the
operator-facing API contract.

These models are pure dataclasses-by-Pydantic — no behaviour,
no I/O. The actual paginate-the-query logic lives in
:mod:`romarr.api.pagination`; the global error handler that
produces ``ErrorEnvelope`` responses lives in
:mod:`romarr.api.error_handlers`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Pagination


SortDirection = Literal["asc", "desc"]


class PaginationEnvelope[RecordT](BaseModel):
    """Canonical list-endpoint response (FR-007).

    Every list endpoint in the project (Game, Release, History,
    Indexer, Notification, JobRun, ...) returns this exact
    shape. The frontend's TanStack Query layer relies on the
    keys being identical across resources.

    ``populate_by_name=True`` lets the schema validate input
    dicts whose keys are either the snake_case Python field
    names or the camelCase aliases. FastAPI's response_model
    machinery dumps a returned envelope to dict with snake_case
    keys (regardless of ``response_model_by_alias``) before
    revalidating; without ``populate_by_name`` that revalidation
    would fail because the aliases would be missing.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    page: int = Field(ge=1)
    page_size: int = Field(alias="pageSize", ge=1, le=1000)
    sort_key: str = Field(alias="sortKey")
    sort_direction: SortDirection = Field(alias="sortDirection")
    total_records: int = Field(alias="totalRecords", ge=0)
    records: list[RecordT]


class ErrorEnvelope(BaseModel):
    """Canonical error response (FR-010).

    The ``errorCode`` field is a stable string token the UI can
    branch on (e.g. ``"unknown_command"``); ``errorMessage`` is
    the human-readable summary; ``details`` is a free-form
    payload for validation errors / retry hints.
    """

    model_config = ConfigDict(frozen=True)

    error_message: str = Field(alias="errorMessage")
    error_code: str | None = Field(alias="errorCode", default=None)
    details: dict[str, Any] | None = None


__all__ = [
    "ErrorEnvelope",
    "PaginationEnvelope",
    "SortDirection",
]
