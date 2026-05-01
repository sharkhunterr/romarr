"""Per-(notification, event) dispatch (FR-008..FR-015, US8.1).

The :class:`EventChannel` from slice 2 owns the per-notification
fan-out — each subscribed notification has its own queue and
its own dispatcher task so a slow target doesn't backpressure a
fast one. This module supplies the **callback** each of those
tasks runs: take one event, decide whether the notification
fires, render, send, and write the audit row.

The decision sequence is:

  1. ``notification.enabled`` — operator-disabled notifications
     never fire (T038).
  2. **Event-flag filter** — the per-event flag (``on_grab``,
     ``on_import``, ...) on the row must be ``True`` (FR-008,
     T035).
  3. **Health-severity filter** — for ``OnHealthIssue`` only,
     ``include_health_warnings`` and ``include_health_errors``
     gate by severity so operators can opt out of the noisy
     half without unsubscribing entirely.
  4. **Tag intersection** — non-empty ``notification.tags``
     must overlap with the event's game tags (FR-014, T036).
     Empty ``notification.tags`` matches every event (FR-015,
     T037). Events without a ``game`` namespace (``OnFail``,
     ``OnDatUpdate``) bypass tag filtering.
  5. **Render + transport** — the URL scheme picks the
     transport: ``json``/``jsons`` → Sonarr-format webhook;
     anything else → Apprise.
  6. **Audit** — ``last_used_at`` / ``last_status`` /
     ``last_error`` updated in place on the ORM row. The caller
     is responsible for committing.

The transport callables are injected so unit tests can stub
them. The default values pulled from
:mod:`romarr.notifications.apprise_wrapper` and
:mod:`romarr.notifications.webhook` make the production wiring
zero-config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from romarr.notifications.apprise_wrapper import AppriseSendResult
from romarr.notifications.apprise_wrapper import send as default_apprise_send
from romarr.notifications.errors import WebhookRetryExhausted
from romarr.notifications.templates.payload_builders import (
    build_apprise_message,
    build_sonarr_webhook_body,
)
from romarr.notifications.types import OnHealthIssuePayload
from romarr.notifications.webhook import WebhookSendResult
from romarr.notifications.webhook import send_webhook as default_send_webhook

if TYPE_CHECKING:
    from pydantic import BaseModel

    from romarr.notifications.models import Notification

_logger = logging.getLogger(__name__)

_WEBHOOK_SCHEMES: frozenset[str] = frozenset({"json", "jsons"})


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of one :func:`dispatch_to_notification` call.

    ``delivered`` is True iff a transport reported success.
    ``skip_reason`` is a stable string token explaining why the
    event was filtered out before any transport call (None when
    delivery was attempted).
    """

    delivered: bool
    skip_reason: str | None


class _AppriseSender(Protocol):
    async def __call__(
        self,
        *,
        notification: Notification,
        title: str,
        body: str,
        notify_type: str = ...,
    ) -> AppriseSendResult: ...


class _WebhookSender(Protocol):
    async def __call__(
        self,
        *,
        notification: Notification,
        target_url: str,
        payload_dict: dict[str, Any],
    ) -> WebhookSendResult: ...


# ---------------------------------------------------------------------------
# Public entry point


async def dispatch_to_notification(
    *,
    notification: Notification,
    event: BaseModel,
    send_apprise: _AppriseSender = default_apprise_send,
    send_webhook: _WebhookSender = default_send_webhook,
) -> DispatchOutcome:
    """Route ``event`` to ``notification`` if filters pass.

    Updates ``notification.last_used_at`` / ``last_status`` /
    ``last_error`` in place. Returns a :class:`DispatchOutcome`
    so the channel-level callback can log structured outcomes
    without re-reading the row.
    """
    if not notification.enabled:
        return DispatchOutcome(delivered=False, skip_reason="disabled")

    if not _matches_event_flag(notification, event):
        return DispatchOutcome(
            delivered=False, skip_reason="event_flag_off"
        )

    if isinstance(
        event, OnHealthIssuePayload
    ) and not _matches_health_severity(notification, event):
        return DispatchOutcome(
            delivered=False, skip_reason="health_severity_filtered"
        )

    if not _matches_tag_filter(notification, event):
        return DispatchOutcome(
            delivered=False, skip_reason="tag_filter_no_match"
        )

    delivered = await _send_and_record(
        notification=notification,
        event=event,
        send_apprise=send_apprise,
        send_webhook=send_webhook,
    )
    return DispatchOutcome(delivered=delivered, skip_reason=None)


# ---------------------------------------------------------------------------
# Filtering


_EVENT_FLAG_FOR_TYPE: dict[str, str] = {
    "OnGrab": "on_grab",
    "OnImport": "on_import",
    "OnUpgrade": "on_upgrade",
    "OnFail": "on_fail",
    "OnHealthIssue": "on_health_issue",
    "OnDatUpdate": "on_dat_update",
    "OnGameAdded": "on_game_added",
}


def _matches_event_flag(
    notification: Notification, event: BaseModel
) -> bool:
    event_type_value = _event_type_value(event)
    if event_type_value is None:
        return False
    flag_name = _EVENT_FLAG_FOR_TYPE.get(event_type_value)
    if flag_name is None:
        return False
    return bool(getattr(notification, flag_name, False))


def _event_type_value(event: BaseModel) -> str | None:
    """Read ``event.event_type`` whether it's a :class:`StrEnum`
    member, a plain string, or absent (returns None)."""
    raw = getattr(event, "event_type", None)
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    return str(value)


def _matches_health_severity(
    notification: Notification, event: OnHealthIssuePayload
) -> bool:
    """Operators can opt out of warning-level health alerts while
    still receiving errors (and vice-versa). Recovery events
    inherit the side they came from — recovering from a warning
    only fires when ``include_health_warnings`` is True; same
    for errors. This means a notification with both flags off
    but ``on_health_issue=True`` wouldn't have made it past the
    event-flag filter; we don't need a fallback here."""
    if event.severity == "warning":
        return notification.include_health_warnings
    if event.severity == "error":
        return notification.include_health_errors
    # severity == "recovered": route by the previous status
    if event.previous_status.value == "warning":
        return notification.include_health_warnings
    if event.previous_status.value == "error":
        return notification.include_health_errors
    return True


def _matches_tag_filter(
    notification: Notification, event: BaseModel
) -> bool:
    """FR-014 / FR-015. Empty ``notification.tags`` matches every
    event. Events without a ``game`` namespace bypass the
    filter — there's nothing to intersect."""
    notification_tags = list(notification.tags or [])
    if not notification_tags:
        return True
    game = getattr(event, "game", None)
    if game is None:
        return True
    game_tags = tuple(getattr(game, "tags", ()) or ())
    return any(tag in game_tags for tag in notification_tags)


# ---------------------------------------------------------------------------
# Sending + audit


async def _send_and_record(
    *,
    notification: Notification,
    event: BaseModel,
    send_apprise: _AppriseSender,
    send_webhook: _WebhookSender,
) -> bool:
    """Pick the transport based on URL scheme, render, send,
    update audit columns. Returns True on success."""
    success = False
    error_message: str | None = None
    try:
        if notification.apprise_url_scheme in _WEBHOOK_SCHEMES:
            success, error_message = await _send_webhook(
                notification=notification,
                event=event,
                send_webhook=send_webhook,
            )
        else:
            success, error_message = await _send_apprise(
                notification=notification,
                event=event,
                send_apprise=send_apprise,
            )
    except WebhookRetryExhausted as exc:
        success = False
        error_message = str(exc)
    except Exception as exc:
        # Catch-all so one bad target can't crash the dispatcher
        # task. The structured message lands on last_error so
        # the operator can see it in the UI.
        _logger.exception(
            "notification dispatch raised for notification_id=%s",
            getattr(notification, "id", None),
        )
        success = False
        error_message = f"{exc.__class__.__name__}: {exc}"

    notification.last_used_at = datetime.now(UTC)
    notification.last_status = "success" if success else "failed"
    notification.last_error = None if success else error_message
    return success


async def _send_apprise(
    *,
    notification: Notification,
    event: BaseModel,
    send_apprise: _AppriseSender,
) -> tuple[bool, str | None]:
    body = build_apprise_message(payload=event, notification=notification)
    title = _title_for_event(event)
    notify_type = _notify_type_for_event(event)
    result = await send_apprise(
        notification=notification,
        title=title,
        body=body,
        notify_type=notify_type,
    )
    return result.success, result.error_message


async def _send_webhook(
    *,
    notification: Notification,
    event: BaseModel,
    send_webhook: _WebhookSender,
) -> tuple[bool, str | None]:
    body = build_sonarr_webhook_body(
        payload=event, notification=notification
    )
    target_url = _webhook_target_url(notification)
    result = await send_webhook(
        notification=notification,
        target_url=target_url,
        payload_dict=body,
    )
    return result.success, result.error_message


def _webhook_target_url(notification: Notification) -> str:
    """Decrypt the Apprise URL stored as ``json://hooks.example/p``
    and convert to ``https://hooks.example/p`` for httpx.

    The conversion is intentionally minimal — Apprise's full
    ``json://`` parse logic supports tag/header overrides we
    don't currently surface; the dispatcher sticks to the URL
    proper. A future slice can extend if operators report needs.
    """
    from romarr.metadata.encryption import decrypt

    plaintext = decrypt(notification.apprise_url_encrypted).decode("utf-8")
    if plaintext.startswith("json://"):
        return "http://" + plaintext.removeprefix("json://")
    if plaintext.startswith("jsons://"):
        return "https://" + plaintext.removeprefix("jsons://")
    return plaintext


def _title_for_event(event: BaseModel) -> str:
    """Operator-facing title — short, one line. The body carries
    the rendered template."""
    event_type_value = _event_type_value(event) or "Event"
    return f"Romarr — {event_type_value}"


def _notify_type_for_event(event: BaseModel) -> str:
    """Map event semantics to Apprise's notify_type slots:
    info / success / warning / failure."""
    event_type_value = _event_type_value(event)
    if event_type_value in ("OnImport", "OnUpgrade", "OnGameAdded"):
        return "success"
    if event_type_value == "OnFail":
        return "failure"
    if event_type_value == "OnHealthIssue":
        severity = getattr(event, "severity", "warning")
        if severity == "error":
            return "failure"
        if severity == "recovered":
            return "success"
        return "warning"
    return "info"


async def trigger_test(
    notification: Notification,
    *,
    send_apprise: _AppriseSender = default_apprise_send,
    send_webhook: _WebhookSender = default_send_webhook,
) -> DispatchOutcome:
    """Synthesize an :class:`OnImportPayload` with placeholder
    fields and run it through :func:`dispatch_to_notification`.

    The synthetic event uses fixed sentinel values so the
    operator can recognise it ("Test Game", "Test Release") and
    so the test endpoint produces a deterministic body. The
    notification's filters (``enabled``, event-flag, tags) are
    bypassed: the operator-pressed test button asserts "send
    one regardless of subscription state" — that's the whole
    point of the endpoint (FR-016).

    Returns the same :class:`DispatchOutcome` shape as a real
    event so the API can surface ``success`` and
    ``error_message`` directly.
    """
    from romarr.notifications.types import (  # local to avoid cycle
        DumpRef,
        GameRef,
        OnImportPayload,
        ReleaseRef,
    )

    payload = OnImportPayload(
        game=GameRef(
            id=0,
            title="Test Game",
            platform_slug="test",
            platform_name="Test Platform",
            igdb_id=None,
            tags=(),
        ),
        release=ReleaseRef(
            id=0,
            name="Test Release",
            region="USA",
            naming_convention="no-intro",
        ),
        dump=DumpRef(path="/test/path", dat_verified=True),
    )

    # Bypass the filter chain so a notification that hasn't
    # subscribed to OnImport (or whose tags don't intersect)
    # still receives the test message — the operator pressed
    # "Test" and expects something to land.
    delivered = await _send_and_record(
        notification=notification,
        event=payload,
        send_apprise=send_apprise,
        send_webhook=send_webhook,
    )
    return DispatchOutcome(delivered=delivered, skip_reason=None)


__all__ = ["DispatchOutcome", "dispatch_to_notification", "trigger_test"]
