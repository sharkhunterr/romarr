"""Import pipeline subsystem (spec 008).

Post-download-complete workflow: watch → extract → hash → DAT
match → identify → game match → multi-disc → profile gate →
render filename → atomic move/hardlink → DB update → lifecycle →
notify. The most operationally critical pipeline in Romarr.

Slice 1 ships SCAF + PERS — module skeleton, errors, value types,
in-process advisory lock, ``ImportHistory`` SQLAlchemy model,
Alembic migration ``0008``, and the orchestrator stub. Each
pipeline step's implementation lands in its own slice in
subsequent passes.
"""

from romarr.importer.errors import (
    ExtractError,
    GameNotMatched,
    ImporterError,
    LockTimeout,
    MoveError,
    ProfileRejected,
    WebhookAuthError,
)
from romarr.importer.locks import ImportLockManager
from romarr.importer.orchestrator import (
    run_import,
    start_watcher,
    stop_watcher,
)
from romarr.importer.types import (
    ImportContext,
    ImportOutcome,
    ImportSource,
    LifecycleAction,
    LifecyclePolicy,
    MultiDiscGroup,
    RejectionReason,
)

__all__ = [
    "ExtractError",
    "GameNotMatched",
    "ImportContext",
    "ImportLockManager",
    "ImportOutcome",
    "ImportSource",
    "ImporterError",
    "LifecycleAction",
    "LifecyclePolicy",
    "LockTimeout",
    "MoveError",
    "MultiDiscGroup",
    "ProfileRejected",
    "RejectionReason",
    "WebhookAuthError",
    "run_import",
    "start_watcher",
    "stop_watcher",
]
