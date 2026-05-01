"""Notifications & Health subsystem (spec 011).

Two subsystems share this module:

  * **Notifications**: per-event Apprise dispatch + Sonarr-format
    webhook target. Operator configures one or more notification
    targets via ``/api/v3/notification*``; the dispatcher
    consumes events from spec 008's importer event bus, spec
    009's library exporters, spec 007's search engine, the DAT
    auto-refresh, and the metadata aggregator.
  * **Health Engine**: periodic component probes (indexers,
    download clients, libraries, DAT freshness, DB, metadata)
    feed the ``health_check`` table; the
    ``GET /api/v3/health`` endpoint serves the in-memory
    snapshot, and a debounced ``OnHealthIssue`` event fires on
    every status transition.

Slice 1 ships SCAF + PERS — module skeleton, errors, value
types (7 event payload models + ``EventPayload`` discriminated
union), SQLAlchemy 2.0 models for the two tables, Pydantic
``Read/Create/Update`` schemas with cross-field validators, and
Alembic migration ``0011``.

Channel + Apprise wrapper + webhook target + templates +
dispatcher + health engine + API + lifespan wiring land in
subsequent slices.
"""

from romarr.notifications.errors import (
    AppriseInvalidUrl,
    HealthCheckTimeout,
    NotificationError,
    TemplateError,
    WebhookRetryExhausted,
)
from romarr.notifications.types import (
    ComponentCategory,
    DownloadClientRef,
    DumpRef,
    EventPayload,
    EventType,
    GameRef,
    HealthCheckResult,
    HealthSnapshot,
    HealthStatus,
    IndexerRef,
    OnDatUpdatePayload,
    OnFailPayload,
    OnGameAddedPayload,
    OnGrabPayload,
    OnHealthIssuePayload,
    OnImportPayload,
    OnUpgradePayload,
    ReleaseRef,
)

__all__ = [
    "AppriseInvalidUrl",
    "ComponentCategory",
    "DownloadClientRef",
    "DumpRef",
    "EventPayload",
    "EventType",
    "GameRef",
    "HealthCheckResult",
    "HealthCheckTimeout",
    "HealthSnapshot",
    "HealthStatus",
    "IndexerRef",
    "NotificationError",
    "OnDatUpdatePayload",
    "OnFailPayload",
    "OnGameAddedPayload",
    "OnGrabPayload",
    "OnHealthIssuePayload",
    "OnImportPayload",
    "OnUpgradePayload",
    "ReleaseRef",
    "TemplateError",
    "WebhookRetryExhausted",
]
