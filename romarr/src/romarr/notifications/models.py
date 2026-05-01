"""SQLAlchemy models for the notifications feature (spec 011).

Two tables:

  * ``notification`` — operator-configured Apprise URL +
    per-event subscription flags + tag filters + optional
    Jinja2 template overrides.
  * ``health_check`` — current state per component (one row per
    component, debouncer reads ``last_emitted_state``).

No FKs into other features; both tables are standalone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_LAST_STATUS_CHECK = (
    "last_status IS NULL OR last_status IN ('success','failed','partial')"
)
_HEALTH_STATUS_CHECK = "status IN ('ok','warning','error')"
_LAST_EMITTED_STATE_CHECK = (
    "last_emitted_state IS NULL OR "
    "last_emitted_state IN ('ok','warning','error')"
)


class Notification(Base, TimestampMixin):
    """One operator-configured notification target.

    The ``apprise_url_encrypted`` blob holds the Fernet-wrapped
    URL; ``apprise_url_scheme`` keeps the prefix in plaintext so
    the read schema can render ``discord://...`` in the UI without
    decrypting on every list call.
    """

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    apprise_url_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    apprise_url_scheme: Mapped[str] = mapped_column(String(32), nullable=False)

    # Event subscription flags
    on_grab: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    on_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    on_upgrade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    on_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    on_health_issue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    on_dat_update: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    on_game_added: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_health_warnings: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_health_errors: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Optional per-event Jinja2 template overrides. NULL = use the
    # default template from ``romarr.notifications.templates``.
    on_grab_format: Mapped[str | None] = mapped_column(String, nullable=True)
    on_import_format: Mapped[str | None] = mapped_column(String, nullable=True)
    on_upgrade_format: Mapped[str | None] = mapped_column(String, nullable=True)
    on_fail_format: Mapped[str | None] = mapped_column(String, nullable=True)
    on_health_issue_format: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    on_dat_update_format: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    on_game_added_format: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Audit / health
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("name", name="uq_notification_name"),
        CheckConstraint(_LAST_STATUS_CHECK, name="ck_notification_last_status"),
        Index("idx_notification_enabled", "enabled"),
    )


class HealthCheck(Base, TimestampMixin):
    """Per-component current state.

    The ``last_emitted_state`` column survives process restarts
    (Q2 clarification) so a flapping-then-restarted Romarr doesn't
    re-spam the operator: the engine compares against the
    persisted value, not against in-memory state.
    """

    __tablename__ = "health_check"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    severity_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Debouncer state (Q2): persisted across process restarts so
    # the engine compares the new probe result against this column,
    # not in-memory state.
    last_emitted_state: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    last_emitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("component", name="uq_health_check_component"),
        CheckConstraint(_HEALTH_STATUS_CHECK, name="ck_health_check_status"),
        CheckConstraint(
            _LAST_EMITTED_STATE_CHECK,
            name="ck_health_check_last_emitted_state",
        ),
        Index("idx_health_check_status", "status"),
        Index(
            "idx_health_check_severity_changed_at", "severity_changed_at"
        ),
    )


__all__ = ["HealthCheck", "Notification"]
