"""Payload-builder shape tests (T032).

The two on-wire shapes — Apprise message string and Sonarr-
webhook dict — are built from the same ``EventPayload``. This
module locks the contract that:

  * the Apprise builder returns a non-empty ``str`` rendered via
    Jinja, and
  * the Sonarr-webhook builder returns a ``dict`` whose
    ``eventType`` matches the Sonarr field name (``Download``
    for imports, ``OnGrab`` for grabs, etc.).

If anyone refactors the builders into a single function or
reuses the wrong code-path for a target, the type/shape
mismatch fails loudly.
"""

from __future__ import annotations

from romarr.notifications.models import Notification
from romarr.notifications.templates import (
    build_apprise_message,
    build_sonarr_webhook_body,
)
from romarr.notifications.types import (
    DumpRef,
    GameRef,
    OnImportPayload,
    ReleaseRef,
)


def _bare_notification() -> Notification:
    return Notification(
        name="t",
        apprise_url_encrypted=b"",
        apprise_url_scheme="discord",
    )


def _payload() -> OnImportPayload:
    return OnImportPayload(
        game=GameRef(
            id=1,
            title="Sonic",
            platform_slug="megadrive",
            platform_name="Mega Drive",
            igdb_id=42,
        ),
        release=ReleaseRef(id=10, name="Sonic (USA)", region="USA"),
        dump=DumpRef(path="/x", dat_verified=True),
    )


def test_apprise_vs_webhook_differ() -> None:
    """Same payload → string for Apprise, dict for webhook."""
    payload = _payload()
    notif = _bare_notification()
    apprise_body = build_apprise_message(payload=payload, notification=notif)
    webhook_body = build_sonarr_webhook_body(
        payload=payload, notification=notif
    )

    assert isinstance(apprise_body, str)
    assert isinstance(webhook_body, dict)
    assert apprise_body  # non-empty
    # Apprise uses our default template; the rendered prefix is "✅".
    assert apprise_body.startswith("✅")
    # Webhook uses the Sonarr eventType naming.
    assert webhook_body["eventType"] == "Download"


def test_apprise_message_renders_template_variables() -> None:
    payload = _payload()
    notif = _bare_notification()
    body = build_apprise_message(payload=payload, notification=notif)
    assert "Sonic" in body
    assert "Mega Drive" in body


def test_webhook_body_carries_remap_keys() -> None:
    payload = _payload()
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    assert body["series"]["title"] == "Sonic"
    assert body["series"]["tvdbId"] == 42
    assert body["episodes"][0]["episodeNumber"] == 10
