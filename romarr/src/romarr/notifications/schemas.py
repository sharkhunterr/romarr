"""Pydantic schemas for the notifications feature (spec 011).

API surface only. The dispatcher's working state lives in
:mod:`romarr.notifications.types`.

Two cross-field invariants enforced at save time:

  * **At least one event subscribed** (FR-005): a notification
    must have at least one ``on_*`` flag set, otherwise it would
    silently never fire.
  * **Template validates** (FR-013): each non-null ``*_format``
    runs through spec 006's sandboxed ``NamingTemplateEngine``
    validator; unknown variables and forbidden filters surface
    as HTTP 400 at save time, not at dispatch time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)

from romarr.notifications.types import HealthCheckResult, HealthSnapshot

# Re-exported for convenience — consumers call
# ``from romarr.notifications.schemas import HealthSnapshotResponse``.
HealthSnapshotResponse = HealthSnapshot


_EVENT_FLAG_NAMES: tuple[str, ...] = (
    "on_grab",
    "on_import",
    "on_upgrade",
    "on_fail",
    "on_health_issue",
    "on_dat_update",
    "on_game_added",
)


class _NotificationBase(BaseModel):
    """Shared fields between Read / Create / Update."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=128)]
    on_grab: bool = False
    on_import: bool = True
    on_upgrade: bool = True
    on_fail: bool = True
    on_health_issue: bool = True
    on_dat_update: bool = False
    on_game_added: bool = False
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    include_health_warnings: bool = True
    include_health_errors: bool = True

    on_grab_format: str | None = None
    on_import_format: str | None = None
    on_upgrade_format: str | None = None
    on_fail_format: str | None = None
    on_health_issue_format: str | None = None
    on_dat_update_format: str | None = None
    on_game_added_format: str | None = None

    @model_validator(mode="after")
    def _at_least_one_event(self) -> Self:
        """FR-005: at least one ``on_*`` must be true so the
        notification can ever fire."""
        if not any(getattr(self, name) for name in _EVENT_FLAG_NAMES):
            raise ValueError(
                "at least one event flag (on_grab/on_import/on_upgrade/on_fail/"
                "on_health_issue/on_dat_update/on_game_added) must be true"
            )
        return self


class NotificationCreate(_NotificationBase):
    """Payload for ``POST /api/v3/notification``.

    The plaintext Apprise URL arrives as :class:`SecretStr`; the
    handler encrypts it and extracts the scheme prefix before
    handing the row to the model layer."""

    apprise_url: SecretStr


class NotificationUpdate(BaseModel):
    """All fields optional; ``extra='forbid'`` so typos surface."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    apprise_url: SecretStr | None = None
    on_grab: bool | None = None
    on_import: bool | None = None
    on_upgrade: bool | None = None
    on_fail: bool | None = None
    on_health_issue: bool | None = None
    on_dat_update: bool | None = None
    on_game_added: bool | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    include_health_warnings: bool | None = None
    include_health_errors: bool | None = None
    on_grab_format: str | None = None
    on_import_format: str | None = None
    on_upgrade_format: str | None = None
    on_fail_format: str | None = None
    on_health_issue_format: str | None = None
    on_dat_update_format: str | None = None
    on_game_added_format: str | None = None


class NotificationRead(_NotificationBase):
    """Read shape — never exposes ``apprise_url_encrypted``;
    surfaces a redacted ``apprise_url_redacted: '<scheme>://...'``
    so the operator can identify the target without leaking the
    URL's host / token."""

    id: int
    apprise_url_redacted: str
    last_used_at: datetime | None = None
    last_status: Literal["success", "failed", "partial"] | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: Any) -> NotificationRead:
        """Build a :class:`NotificationRead` from a Notification
        ORM row, masking the encrypted URL into the
        ``<scheme>://...`` redacted form."""
        return cls.model_validate(
            {
                "id": row.id,
                "name": row.name,
                "apprise_url_redacted": f"{row.apprise_url_scheme}://...",
                "on_grab": row.on_grab,
                "on_import": row.on_import,
                "on_upgrade": row.on_upgrade,
                "on_fail": row.on_fail,
                "on_health_issue": row.on_health_issue,
                "on_dat_update": row.on_dat_update,
                "on_game_added": row.on_game_added,
                "tags": list(row.tags or []),
                "enabled": row.enabled,
                "include_health_warnings": row.include_health_warnings,
                "include_health_errors": row.include_health_errors,
                "on_grab_format": row.on_grab_format,
                "on_import_format": row.on_import_format,
                "on_upgrade_format": row.on_upgrade_format,
                "on_fail_format": row.on_fail_format,
                "on_health_issue_format": row.on_health_issue_format,
                "on_dat_update_format": row.on_dat_update_format,
                "on_game_added_format": row.on_game_added_format,
                "last_used_at": row.last_used_at,
                "last_status": row.last_status,
                "last_error": row.last_error,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )


class HealthCheckRead(BaseModel):
    """Read shape for the ``health_check`` row — exposes every
    column for the dashboard's per-component view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    component: str
    status: Literal["ok", "warning", "error"]
    message: str | None
    severity_changed_at: datetime
    last_checked_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    last_emitted_state: Literal["ok", "warning", "error"] | None = None
    last_emitted_at: datetime | None = None


class TestNotificationResponse(BaseModel):
    """Response body for ``POST /api/v3/notification/{id}/test``."""

    success: bool
    error_message: str | None = None


__all__ = [
    "HealthCheckRead",
    "HealthCheckResult",
    "HealthSnapshot",
    "HealthSnapshotResponse",
    "NotificationCreate",
    "NotificationRead",
    "NotificationUpdate",
    "TestNotificationResponse",
]
