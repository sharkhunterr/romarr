"""Notification message templates + payload builders (spec 011 — Phase 5 + 4)."""

from romarr.notifications.templates.defaults import DEFAULT_TEMPLATES
from romarr.notifications.templates.payload_builders import (
    build_apprise_message,
    build_sonarr_webhook_body,
)
from romarr.notifications.templates.renderer import (
    render_event,
    validate_template,
)

__all__ = [
    "DEFAULT_TEMPLATES",
    "build_apprise_message",
    "build_sonarr_webhook_body",
    "render_event",
    "validate_template",
]
