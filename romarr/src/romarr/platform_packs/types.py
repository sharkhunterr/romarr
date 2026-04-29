"""Pydantic value types for the platform-packs HTTP layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PackPlatformDiff(_Base):
    """Per-platform projection of an ingest plan.

    The ingest pipeline returns one of these per slug touched by a
    pack apply. ``reason`` is populated when ``action == 'skipped'``
    (e.g., ``"user-overridden"``).
    """

    slug: str
    action: Literal["inserted", "updated", "skipped"]
    reason: str | None = None
    fields_changed: list[str] = Field(default_factory=list)


class PackUploadResult(_Base):
    """Returned by the upload + apply / re-apply endpoints."""

    pack_version: str
    contents_hash: str
    action: Literal["applied", "reapplied", "skipped", "failed"]
    diff: list[PackPlatformDiff] = Field(default_factory=list)
    parsing_strategies_affected: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None


class ValidateResult(_Base):
    """Returned by the ``/validate`` endpoint — same shape as
    :class:`PackUploadResult` but the database state is guaranteed
    untouched and ``action`` carries the would-be outcome."""

    pack_version: str
    contents_hash: str
    action: Literal["would_apply", "would_skip", "would_fail"]
    diff: list[PackPlatformDiff] = Field(default_factory=list)
    parsing_strategies_affected: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    database_state_unchanged: bool = True
    error_message: str | None = None
