"""Value types for the importer pipeline (spec 008).

These are the in-memory shapes the 13-step orchestrator passes
between phases. None of them are persisted directly — they are
the working memory of one ``run_import`` invocation.

Frozen Pydantic models so the orchestrator can rely on inputs
not mutating mid-step (Article XVII — purity by construction
where possible; the orchestrator itself isn't pure but the
values it threads are).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LifecyclePolicy = Literal[
    "hardlink_and_seed", "move_and_remove", "copy_and_keep"
]
ImportSource = Literal["automatic", "manual", "rss", "api", "webhook", "scan"]


class RejectionReason(StrEnum):
    """Structured reasons for ``import_history.error_msg`` and
    ``unidentified_dump.rejection_reason``. Values follow the
    documented ``<phase>:<sub-reason>`` convention so UI filters
    can group by phase.
    """

    EXTRACT_DEPTH_EXCEEDED = "extract:depth-exceeded"
    EXTRACT_BAD_ARCHIVE = "extract:bad-archive"
    EXTRACT_BOMB_DETECTED = "extract:bomb-detected"
    HASH_FAILED = "hash:failed"
    NO_GAME_MATCH = "match:no_game"
    PROFILE_REGION_REJECT = "profile:region"
    PROFILE_LANGUAGE_REJECT = "profile:language"
    PROFILE_DUMP_REJECT = "profile:dump"
    PROFILE_QUALITY_REJECT = "profile:quality"
    REQUIRE_DAT_VERIFIED_FAILED = "profile:quality:require_dat_verified"
    MOVE_HASH_MISMATCH = "move:copy_hash_mismatch"
    MOVE_PERMISSION_ERROR = "move:permission_error"
    MOVE_DISK_FULL = "move:disk_full"
    MOVE_FAILED = "move:failed"
    LOCK_TIMEOUT = "lock:timeout"
    DESTINATION_COLLISION = "destination_collision"
    ROUTING_NO_LIBRARY = "routing:no_library_for_platform"


class ImportContext(BaseModel):
    """Initial context the orchestrator receives — the input to
    :func:`run_import`. Every field after ``source_path`` is
    populated downstream as the pipeline learns more.
    """

    model_config = ConfigDict(frozen=True)

    download_client_id: int | None = None
    download_client_native_id: str | None = None
    source_path: Path
    library_id: int | None = None
    target_library_lifecycle_policy: LifecyclePolicy | None = None
    target_library_keep_dump_history: bool | None = None
    target_library_path: Path | None = None
    correlation_id: UUID
    imported_via: ImportSource
    imported_by: str = "system"
    force: bool = False
    # Slice 369: pre-resolved game / release ids carried from
    # the ``queue_entry`` row when the import comes from a
    # manual grab. Skips the filename-fuzzy game-match step —
    # the operator already told us which game this download
    # was for, and parsing free-form torrent filenames against
    # the catalogue is brittle.
    pre_matched_game_id: int | None = None
    pre_matched_release_id: int | None = None


class MultiDiscGroup(BaseModel):
    """A detected multi-disc set. ``parent_index`` is the index of
    disc 1 in ``member_paths`` (typically 0 after sort). The
    importer creates one parent Release plus one child Release per
    additional member.
    """

    model_config = ConfigDict(frozen=True)

    parent_index: int
    member_paths: tuple[Path, ...]
    detection_signal: Literal["cue_bin", "filename_pattern", "stem_heuristic"]


class LifecycleAction(BaseModel):
    """Post-import cleanup against the originating download client
    (FR-021). The importer emits one of these per successful
    import; the LIFECYCLE step dispatches it.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["tag_imported", "schedule_remove", "noop"]
    download_client_id: int
    download_client_native_id: str
    not_before: datetime | None = None


class ImportOutcome(BaseModel):
    """Final outcome of one ``run_import`` invocation. Mirrors the
    success / failure / coalesced shape of the corresponding
    ``import_history`` row; the ``history_id`` lets the caller
    follow up with the audit trail.
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    coalesced: bool = False
    dest_path: Path | None = None
    dump_id: int | None = None
    release_id: int | None = None
    game_id: int | None = None
    confidence: float | None = None
    warning: str | None = None
    error_msg: str | None = None
    rejection_reason: RejectionReason | None = None
    history_id: int
    correlation_id: UUID
    duration_ms: int = Field(ge=0)


__all__ = [
    "ImportContext",
    "ImportOutcome",
    "ImportSource",
    "LifecycleAction",
    "LifecyclePolicy",
    "MultiDiscGroup",
    "RejectionReason",
]
