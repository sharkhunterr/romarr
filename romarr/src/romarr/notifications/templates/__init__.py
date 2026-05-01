"""Notification message templates (spec 011 — Phase 5)."""

from romarr.notifications.templates.defaults import DEFAULT_TEMPLATES
from romarr.notifications.templates.renderer import (
    render_event,
    validate_template,
)

__all__ = ["DEFAULT_TEMPLATES", "render_event", "validate_template"]
