"""Notification CRUD + test endpoints (FR-023, FR-024, FR-024b).

Routes:

  - GET    /api/v3/notification              — list (any role)
  - GET    /api/v3/notification/schema       — list of supported
    target implementations (apprise / webhook) for the UI's
    "add notification" wizard
  - POST   /api/v3/notification              — create (admin)
  - GET    /api/v3/notification/{id}         — read; URL redacted
  - PUT    /api/v3/notification/{id}         — update (admin)
  - DELETE /api/v3/notification/{id}         — delete (admin)
  - POST   /api/v3/notification/{id}/test    — synthetic dispatch
    (admin — outbound HTTP, same SSRF-rationale as the indexer
    test endpoint; FR-024b)

The plaintext Apprise URL is encrypted at rest (Fernet) and
redacted on every read response so the UI shows the scheme
prefix without leaking the host / token. Operator-supplied
templates are validated at save time so a typo lands as HTTP 400
rather than being recorded forever as `last_error`.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.metadata.encryption import encrypt
from romarr.notifications.apprise_wrapper import validate_url
from romarr.notifications.dispatcher import trigger_test
from romarr.notifications.errors import (
    AppriseInvalidUrl,
    TemplateError,
)
from romarr.notifications.models import Notification
from romarr.notifications.schemas import (
    NotificationCreate,
    NotificationRead,
    NotificationUpdate,
    TestNotificationResponse,
)
from romarr.notifications.templates import validate_template
from romarr.notifications.types import EventType

router = APIRouter(prefix="/api/v3/notification", tags=["Notifications"])


# Map override column → EventType for save-time template validation.
_FORMAT_FIELD_TO_EVENT: dict[str, EventType] = {
    "on_grab_format": EventType.ON_GRAB,
    "on_import_format": EventType.ON_IMPORT,
    "on_upgrade_format": EventType.ON_UPGRADE,
    "on_fail_format": EventType.ON_FAIL,
    "on_health_issue_format": EventType.ON_HEALTH_ISSUE,
    "on_dat_update_format": EventType.ON_DAT_UPDATE,
    "on_game_added_format": EventType.ON_GAME_ADDED,
}


def _validate_template_fields(values: dict[str, Any]) -> None:
    """Validate every non-empty ``*_format`` override against its
    matching event-type stub (FR-013). Raises HTTP 400 on the
    first failing template so the operator knows which one."""
    for field_name, event_type in _FORMAT_FIELD_TO_EVENT.items():
        template_str = values.get(field_name)
        if template_str:
            try:
                validate_template(template_str, event_type=event_type)
            except TemplateError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name}: {exc}",
                ) from exc


def _validate_apprise_url(plaintext_url: str) -> str:
    """Confirm the URL is parseable by Apprise. Raises HTTP 400
    on rejection so the UI can show the structured error.
    Returns the scheme prefix for the audit column."""
    try:
        validate_url(plaintext_url)
    except AppriseInvalidUrl as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    parsed = urlparse(plaintext_url)
    return parsed.scheme or "unknown"


# ---------------------------------------------------------------------------
# Schema descriptor
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=list[dict[str, Any]])
async def list_implementations(
    _principal: Annotated[Principal, Depends(require_readonly)],
) -> list[dict[str, Any]]:
    """Per FR-023, the UI's "add notification" wizard fetches a
    list of supported target implementations. Romarr exposes two:

      * ``apprise`` — operator pastes any Apprise URL
        (``discord://``, ``tgram://``, ``ntfys://``, …) and
        Romarr handles the transport.
      * ``webhook`` — Sonarr v3-format JSON POST to a configured
        URL via the ``json://`` / ``jsons://`` Apprise schemes.
    """
    return [
        {
            "implementation": "apprise",
            "name": "Apprise",
            "description": (
                "Generic Apprise URL — supports Discord, Telegram, "
                "ntfy, Slack, Gotify, email, and many others."
            ),
            "field_label": "Apprise URL",
            "field_placeholder": "discord://...",
        },
        {
            "implementation": "webhook",
            "name": "Webhook (Sonarr v3-compatible)",
            "description": (
                "Sonarr v3-format JSON POST. Use the json:// or "
                "jsons:// scheme; Notifiarr / Homepage / Tautulli "
                "consume the body verbatim."
            ),
            "field_label": "Webhook URL",
            "field_placeholder": "json://hooks.example/path",
        },
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[NotificationRead]:
    rows = (
        await session.execute(
            select(Notification).order_by(Notification.id)
        )
    ).scalars().all()
    return [NotificationRead.from_orm_row(row) for row in rows]


@router.post(
    "",
    response_model=NotificationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    payload: NotificationCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationRead:
    """Create a notification target.

    Validates the Apprise URL via ``Apprise.add(...)`` (FR-004),
    every non-null template via the sandboxed renderer (FR-013),
    and at-least-one-event flag via the schema (FR-005). On
    success, the URL is Fernet-encrypted at rest; only the
    scheme prefix is persisted in plaintext for the read shape.
    """
    plaintext = payload.apprise_url.get_secret_value()
    scheme = _validate_apprise_url(plaintext)
    _validate_template_fields(payload.model_dump())

    row = Notification(
        name=payload.name,
        apprise_url_encrypted=encrypt(plaintext.encode("utf-8")),
        apprise_url_scheme=scheme,
        on_grab=payload.on_grab,
        on_import=payload.on_import,
        on_upgrade=payload.on_upgrade,
        on_fail=payload.on_fail,
        on_health_issue=payload.on_health_issue,
        on_dat_update=payload.on_dat_update,
        on_game_added=payload.on_game_added,
        tags=list(payload.tags),
        enabled=payload.enabled,
        include_health_warnings=payload.include_health_warnings,
        include_health_errors=payload.include_health_errors,
        on_grab_format=payload.on_grab_format,
        on_import_format=payload.on_import_format,
        on_upgrade_format=payload.on_upgrade_format,
        on_fail_format=payload.on_fail_format,
        on_health_issue_format=payload.on_health_issue_format,
        on_dat_update_format=payload.on_dat_update_format,
        on_game_added_format=payload.on_game_added_format,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"notification name already in use: {payload.name}",
        ) from exc
    await session.refresh(row)
    return NotificationRead.from_orm_row(row)


@router.get("/{notification_id}", response_model=NotificationRead)
async def read_notification(
    notification_id: int,
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationRead:
    row = await session.get(Notification, notification_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notification not found",
        )
    return NotificationRead.from_orm_row(row)


@router.put("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: int,
    payload: NotificationUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationRead:
    row = await session.get(Notification, notification_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notification not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "apprise_url" in update_data:
        secret = update_data.pop("apprise_url")
        if secret is not None:
            plaintext = secret.get_secret_value()
            row.apprise_url_scheme = _validate_apprise_url(plaintext)
            row.apprise_url_encrypted = encrypt(plaintext.encode("utf-8"))

    _validate_template_fields(update_data)

    for field, value in update_data.items():
        setattr(row, field, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="notification name conflicts with another row",
        ) from exc
    await session.refresh(row)
    return NotificationRead.from_orm_row(row)


@router.delete(
    "/{notification_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_notification(
    notification_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = await session.get(Notification, notification_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notification not found",
        )
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Test endpoint (FR-016, FR-024b)
# ---------------------------------------------------------------------------


@router.post(
    "/{notification_id}/test",
    response_model=TestNotificationResponse,
)
async def test_notification(
    notification_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TestNotificationResponse:
    """Fire a synthetic ``OnImport`` event with placeholder data
    through the same dispatcher real events use (FR-016).

    Admin-gated because it triggers outbound HTTP to the
    configured URL — same SSRF-rationale as spec 005's
    download-client connectivity test (FR-024b)."""
    row = await session.get(Notification, notification_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notification not found",
        )
    outcome = await trigger_test(row)
    await session.commit()  # persist the audit-row update
    return TestNotificationResponse(
        success=outcome.delivered,
        error_message=row.last_error if not outcome.delivered else None,
    )


__all__ = ["router"]
