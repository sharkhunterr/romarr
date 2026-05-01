"""Domain errors for the notifications subsystem (spec 011).

Domain-specific exception names per Article XII; the
``noqa: N818`` markers acknowledge that some names diverge from
ruff's ``…Error`` convention because they read more naturally
on the call site.
"""

from __future__ import annotations


class NotificationError(Exception):
    """Base class for every domain-level notification failure."""


class AppriseInvalidUrl(NotificationError):  # noqa: N818 — domain-specific
    """The configured Apprise URL fails ``Apprise.add(...)``
    validation. Surfaced at save-time validation (FR-004) and
    again from the test endpoint."""


class TemplateError(NotificationError):
    """Operator-supplied Jinja2 template is invalid (unknown
    variable, forbidden filter, syntax error). The notification
    falls back to the spec 011 default template after recording
    the error on the audit row (FR-013)."""


class WebhookRetryExhausted(NotificationError):  # noqa: N818
    """Sonarr-format webhook target failed all 3 tenacity retry
    attempts. Surfaced as ``last_status='failed'`` on the
    notification row."""


class HealthCheckTimeout(NotificationError):  # noqa: N818
    """A health-check probe didn't return within the per-check
    timeout (default 10 s). The cycle records the component as
    ``warning`` and continues; FR-024 isolates one slow check
    from blocking the rest."""
