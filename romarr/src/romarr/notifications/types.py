"""Value types for the notifications subsystem (spec 011).

Three groups:
  * The ``EventType`` / ``HealthStatus`` / ``ComponentCategory``
    enums every consumer in the project shares.
  * The seven event payload value types — one per event the
    importer / search / library / DAT / metadata layers emit.
  * The aggregate :class:`HealthSnapshot` the
    ``GET /api/v3/health`` endpoint serves.

All payload models are frozen so the dispatcher's serial-per-
notification fan-out can rely on them not mutating mid-template-
render.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_FROZEN: ConfigDict = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Enums


class EventType(StrEnum):
    """The seven event types the notification subsystem dispatches.

    String values match the Sonarr/Radarr ``eventType`` field
    verbatim so the webhook target's payload is a drop-in
    replacement for Notifiarr / Homepage / similar tooling.
    """

    ON_GRAB = "OnGrab"
    ON_IMPORT = "OnImport"
    ON_UPGRADE = "OnUpgrade"
    ON_FAIL = "OnFail"
    ON_HEALTH_ISSUE = "OnHealthIssue"
    ON_DAT_UPDATE = "OnDatUpdate"
    ON_GAME_ADDED = "OnGameAdded"


class HealthStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class ComponentCategory(StrEnum):
    INDEXER = "indexer"
    DOWNLOAD_CLIENT = "downloadclient"
    LIBRARY = "library"
    DAT = "dat"
    DB = "db"
    METADATA = "metadata"
    DISK = "disk"


# ---------------------------------------------------------------------------
# Health


class HealthCheckResult(BaseModel):
    """One probe outcome — what the engine writes back into the
    ``health_check`` table after running a component's check."""

    model_config = _FROZEN

    component: str
    category: ComponentCategory
    status: HealthStatus
    message: str | None = None


class HealthSnapshot(BaseModel):
    """In-memory aggregate the ``/api/v3/health`` endpoint
    returns. ``overall_status`` is the worst per-component
    status across the whole table."""

    model_config = _FROZEN

    overall_status: HealthStatus
    by_category: dict[ComponentCategory, list[HealthCheckResult]]
    refreshed_at: datetime


# ---------------------------------------------------------------------------
# Event-payload reference shapes


class GameRef(BaseModel):
    """Minimal Game data the templates render. Carries
    ``tags`` so the dispatcher can match notifications by
    operator-configured tag list."""

    model_config = _FROZEN

    id: int
    title: str
    platform_slug: str
    platform_name: str
    igdb_id: int | None = None
    tags: tuple[str, ...] = ()


class ReleaseRef(BaseModel):
    model_config = _FROZEN

    id: int
    name: str
    region: str | None = None
    languages: tuple[str, ...] = ()
    revision: str | None = None
    dump_status: str = "unknown"
    naming_convention: str = "unknown"


class DumpRef(BaseModel):
    model_config = _FROZEN

    path: str
    sha1: str | None = None
    crc32: str | None = None
    md5: str | None = None
    size_bytes: int | None = None
    dat_verified: bool = False
    dat_source: str | None = None


class IndexerRef(BaseModel):
    model_config = _FROZEN

    id: int
    name: str


class DownloadClientRef(BaseModel):
    model_config = _FROZEN

    id: int
    name: str
    type: str


# ---------------------------------------------------------------------------
# Per-event payloads (one per EventType)


class OnGrabPayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_GRAB] = EventType.ON_GRAB
    game: GameRef
    release: ReleaseRef
    indexer: IndexerRef
    download_client: DownloadClientRef
    download_id: str
    custom_format_score: int = 0


class OnImportPayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_IMPORT] = EventType.ON_IMPORT
    game: GameRef
    release: ReleaseRef
    dump: DumpRef
    is_upgrade: bool = False


class OnUpgradePayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_UPGRADE] = EventType.ON_UPGRADE
    game: GameRef
    old_release: ReleaseRef
    new_release: ReleaseRef
    new_dump: DumpRef


class OnFailPayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_FAIL] = EventType.ON_FAIL
    release: ReleaseRef
    error_msg: str
    download_client: DownloadClientRef | None = None


class OnHealthIssuePayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_HEALTH_ISSUE] = EventType.ON_HEALTH_ISSUE
    component: str
    category: ComponentCategory
    severity: Literal["warning", "error", "recovered"]
    previous_status: HealthStatus
    current_status: HealthStatus
    message: str


class OnDatUpdatePayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_DAT_UPDATE] = EventType.ON_DAT_UPDATE
    source: str
    platform: str
    entries_count: int
    version: str


class OnGameAddedPayload(BaseModel):
    model_config = _FROZEN

    event_type: Literal[EventType.ON_GAME_ADDED] = EventType.ON_GAME_ADDED
    game: GameRef
    library_id: int | None = None


EventPayload = Annotated[
    OnGrabPayload
    | OnImportPayload
    | OnUpgradePayload
    | OnFailPayload
    | OnHealthIssuePayload
    | OnDatUpdatePayload
    | OnGameAddedPayload,
    Field(discriminator="event_type"),
]
"""Discriminated union the dispatcher accepts. Pydantic picks the
right concrete model from the ``event_type`` literal so the
template renderer always sees the right shape."""


__all__ = [
    "ComponentCategory",
    "DownloadClientRef",
    "DumpRef",
    "EventPayload",
    "EventType",
    "GameRef",
    "HealthCheckResult",
    "HealthSnapshot",
    "HealthStatus",
    "IndexerRef",
    "OnDatUpdatePayload",
    "OnFailPayload",
    "OnGameAddedPayload",
    "OnGrabPayload",
    "OnHealthIssuePayload",
    "OnImportPayload",
    "OnUpgradePayload",
    "ReleaseRef",
]
