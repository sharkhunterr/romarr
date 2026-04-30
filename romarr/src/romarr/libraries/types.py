"""Value types for the libraries subsystem (spec 009).

These are the in-memory shapes the routing engine, the heartbeat
loop, the scanner, and the exporters operate on. None of them are
persisted directly — they are read once from the
:class:`romarr.libraries.models.Library` row and handed around as
frozen Pydantic snapshots so the downstream code never re-reads
the DB on the hot path.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LifecyclePolicy = Literal[
    "hardlink_and_seed",
    "move_and_remove",
    "copy_and_keep",
]
"""The three lifecycle modes a library can apply to a successful
import. ``hardlink_and_seed`` is the default and matches Sonarr /
Radarr's preferred behaviour."""


class LibraryStatus(StrEnum):
    """Result of the most recent heartbeat probe."""

    OK = "ok"
    UNAVAILABLE = "unavailable"


class LibrarySnapshot(BaseModel):
    """Slim, frozen view of a :class:`Library` row.

    Preloaded by the router and the heartbeat loop so the hot path
    never re-reads the DB. Held by reference inside
    :class:`romarr.libraries.LibraryRegistry`.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    path: Path
    status: LibraryStatus
    platforms_restricted: bool
    accepted_platform_ids: frozenset[int]
    quality_profile_id: int
    region_profile_id: int
    dump_profile_id: int
    language_profile_id: int
    naming_profile_id: int
    use_hardlinks: bool
    lifecycle_policy: LifecyclePolicy
    keep_dump_history: bool
    min_disk_free_gb: int
    preserve_archive: bool


class RoutingChoice(BaseModel):
    """Outcome of :func:`romarr.libraries.route_to_library`.

    ``chosen_library_id`` is None when the file cannot be routed —
    ``rejection_reason`` then carries the operator-facing string.
    """

    model_config = ConfigDict(frozen=True)

    chosen_library_id: int | None
    chosen_via: Literal[
        "only_eligible",
        "profile_match",
        "lower_id_tiebreak",
        "no_eligible_library",
    ]
    candidates_considered: tuple[int, ...] = Field(default_factory=tuple)
    rejection_reason: str | None = None


class ScanProgress(BaseModel):
    """Progress envelope for a single scan run.

    Persisted summary lives on ``library.last_scan_status`` /
    ``last_full_scan_at`` / ``last_incremental_scan_at``; the live
    progress is reported through the WebSocket bus.
    """

    model_config = ConfigDict(frozen=True)

    library_id: int
    scan_kind: Literal["full", "incremental"]
    files_seen: int
    files_processed: int
    files_orphaned: int
    started_at: datetime
    last_event_at: datetime
    finished_at: datetime | None = None
    last_status: Literal["running", "success", "partial", "failed"] = "running"
    last_error: str | None = None


class ExporterOutcome(BaseModel):
    """Result of one exporter run on one (library, platform) pair.

    Exporters always emit one of these so the orchestrator can
    aggregate them into a per-library ``ExporterRunReport`` for the
    OnExporterRun notification (spec 011).
    """

    model_config = ConfigDict(frozen=True)

    name: Literal["romm", "esde", "pegasus", "launchbox"]
    library_id: int
    platform_id: int | None
    success: bool
    files_emitted: int
    error_message: str | None
    duration_ms: int
    finished_at: datetime
