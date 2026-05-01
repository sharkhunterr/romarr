"""Dispatcher tests (T035-T040, FR-014/FR-015, US8.1).

The dispatcher is the per-(notification, event) decision point:

  1. ``notification.enabled == False`` ⇒ skip (T038);
  2. event-type flag (``on_grab`` / ``on_import`` / …) on the
     notification row must be ``True`` (T035);
  3. tag intersection: non-empty ``notification.tags`` must
     overlap with ``event.game.tags`` (T036, FR-014);
  4. empty ``notification.tags`` matches every event (T037,
     FR-015);
  5. for ``OnUpgrade``, the dispatcher receives two events from
     the upstream emitter — ``OnImport`` and ``OnUpgrade`` —
     and a notification subscribed to both flags fires twice
     (T039, US8.1);
  6. successful delivery sets ``last_status='success'``;
     failure sets ``'failed'`` with ``last_error`` populated
     (T040).

The transport — Apprise vs Sonarr-format webhook — is injected
via callables so these tests don't need a real Apprise URL or
HTTP server. The integration with ``apprise_wrapper.send`` and
``webhook.send_webhook`` lives in the dispatcher module itself
and is exercised by the channel-level tests in slice 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from romarr.config.settings import get_settings
from romarr.metadata.encryption import encrypt
from romarr.notifications.apprise_wrapper import AppriseSendResult
from romarr.notifications.dispatcher import (
    DispatchOutcome,
    dispatch_to_notification,
)
from romarr.notifications.models import Notification
from romarr.notifications.types import (
    DownloadClientRef,
    DumpRef,
    GameRef,
    IndexerRef,
    OnFailPayload,
    OnGameAddedPayload,
    OnGrabPayload,
    OnImportPayload,
    OnUpgradePayload,
    ReleaseRef,
)
from romarr.notifications.webhook import WebhookSendResult

# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The webhook-routing tests decrypt the URL stored on the
    ``Notification`` row, so the auth secret must be set even
    though most tests in this module never reach the transport
    layer."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@dataclass
class FakeApprise:
    """Records every call to the apprise transport."""

    calls: list[tuple[Notification, str]]
    result: AppriseSendResult = field(
        default_factory=lambda: AppriseSendResult(success=True)
    )

    async def __call__(
        self,
        *,
        notification: Notification,
        title: str,
        body: str,
        notify_type: str = "info",
    ) -> AppriseSendResult:
        self.calls.append((notification, body))
        return self.result


@dataclass
class FakeWebhook:
    """Records every call to the webhook transport."""

    calls: list[tuple[Notification, dict[str, Any]]]
    result: WebhookSendResult = field(
        default_factory=lambda: WebhookSendResult(
            success=True, status_code=200
        )
    )

    async def __call__(
        self,
        *,
        notification: Notification,
        target_url: str,
        payload_dict: dict[str, Any],
    ) -> WebhookSendResult:
        self.calls.append((notification, payload_dict))
        return self.result


@pytest.fixture
def apprise_stub() -> FakeApprise:
    return FakeApprise(calls=[])


@pytest.fixture
def webhook_stub() -> FakeWebhook:
    return FakeWebhook(calls=[])


def _notification(**overrides: Any) -> Notification:
    """Build an in-memory Notification matching the test scenario.
    The dispatcher reads ORM attributes directly; persistence is
    not exercised here. The URL is encrypted with the patched
    test secret so the webhook-routing tests can decrypt it."""
    base = {
        "name": "test",
        "apprise_url_encrypted": encrypt(
            b"json://hooks.example/abc"
        ),
        "apprise_url_scheme": "discord",
        "on_grab": True,
        "on_import": True,
        "on_upgrade": True,
        "on_fail": True,
        "on_health_issue": True,
        "on_dat_update": True,
        "on_game_added": True,
        "tags": [],
        "enabled": True,
        "include_health_warnings": True,
        "include_health_errors": True,
    }
    base.update(overrides)
    return Notification(**base)


def _game(tags: tuple[str, ...] = ()) -> GameRef:
    return GameRef(
        id=1,
        title="Sonic the Hedgehog",
        platform_slug="megadrive",
        platform_name="Sega Mega Drive",
        igdb_id=42,
        tags=tags,
    )


def _release() -> ReleaseRef:
    return ReleaseRef(
        id=10, name="Sonic the Hedgehog (USA)", region="USA"
    )


def _grab_event(tags: tuple[str, ...] = ()) -> OnGrabPayload:
    return OnGrabPayload(
        game=_game(tags),
        release=_release(),
        indexer=IndexerRef(id=1, name="X"),
        download_client=DownloadClientRef(id=1, name="X", type="qbittorrent"),
        download_id="abc",
    )


def _import_event(tags: tuple[str, ...] = ()) -> OnImportPayload:
    return OnImportPayload(
        game=_game(tags),
        release=_release(),
        dump=DumpRef(path="/x", dat_verified=True),
    )


# ---------------------------------------------------------------------------
# T035 — event-flag filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_flag_filter_blocks_unsubscribed(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """``on_grab=False`` ⇒ OnGrab event NOT delivered;
    ``on_import=True`` ⇒ OnImport delivered."""
    notif = _notification(on_grab=False, on_import=True)

    grab_outcome = await dispatch_to_notification(
        notification=notif,
        event=_grab_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    import_outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert grab_outcome.delivered is False
    assert grab_outcome.skip_reason == "event_flag_off"
    assert import_outcome.delivered is True
    assert len(apprise_stub.calls) == 1
    assert "Sonic" in apprise_stub.calls[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_factory,flag_name",
    [
        (_grab_event, "on_grab"),
        (_import_event, "on_import"),
    ],
)
async def test_each_event_flag_blocks_its_own_event(
    event_factory: Any,
    flag_name: str,
    apprise_stub: FakeApprise,
    webhook_stub: FakeWebhook,
) -> None:
    notif = _notification(**{flag_name: False})
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event_factory(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert apprise_stub.calls == []


# ---------------------------------------------------------------------------
# T036 — tag intersection (FR-014)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_filter_intersection_match(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification(tags=["family-friendly"])
    event = _import_event(tags=("family-friendly", "platformer"))
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True
    assert len(apprise_stub.calls) == 1


@pytest.mark.asyncio
async def test_tag_filter_no_intersection_skips(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """Notification subscribed to ``family-friendly`` doesn't fire
    when the game has no overlapping tags."""
    notif = _notification(tags=["family-friendly"])
    event = _import_event(tags=("platformer",))
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert outcome.skip_reason == "tag_filter_no_match"
    assert apprise_stub.calls == []


@pytest.mark.asyncio
async def test_tag_filter_empty_game_tags_skips(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """FR-014: notification with non-empty tags + game with empty
    tags ⇒ NOT delivered."""
    notif = _notification(tags=["family-friendly"])
    event = _import_event(tags=())
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False


# ---------------------------------------------------------------------------
# T037 — empty notification.tags matches every event (FR-015)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_tags_match_all(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification(tags=[])
    # Every event below has different game tags or none at all.
    events = [
        _import_event(tags=()),
        _import_event(tags=("platformer",)),
        _import_event(tags=("family-friendly", "platformer")),
        _grab_event(tags=()),
    ]
    for event in events:
        outcome = await dispatch_to_notification(
            notification=notif,
            event=event,
            send_apprise=apprise_stub,
            send_webhook=webhook_stub,
        )
        assert outcome.delivered is True
    assert len(apprise_stub.calls) == len(events)


# ---------------------------------------------------------------------------
# T038 — disabled notification never delivers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_notification_never_delivers(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification(enabled=False)
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert outcome.skip_reason == "disabled"
    assert apprise_stub.calls == []


# ---------------------------------------------------------------------------
# T039 — OnUpgrade fires both events for a notification subscribed to both
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_fires_both_events(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """The importer emits OnImport AND OnUpgrade for an upgrade.
    A notification subscribed to both flags receives two
    messages — one per event — because the dispatcher's filter
    is per-event-type, not per-import."""
    notif = _notification(on_import=True, on_upgrade=True)
    import_event = OnImportPayload(
        game=_game(),
        release=_release(),
        dump=DumpRef(path="/x", dat_verified=True),
        is_upgrade=True,
    )
    upgrade_event = OnUpgradePayload(
        game=_game(),
        old_release=_release(),
        new_release=_release(),
        new_dump=DumpRef(path="/x", dat_verified=True),
    )
    for event in (import_event, upgrade_event):
        outcome = await dispatch_to_notification(
            notification=notif,
            event=event,
            send_apprise=apprise_stub,
            send_webhook=webhook_stub,
        )
        assert outcome.delivered is True
    assert len(apprise_stub.calls) == 2


# ---------------------------------------------------------------------------
# T040 — last_status / last_error / last_used_at recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_records_last_status_on_success(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification()
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True
    assert notif.last_status == "success"
    assert notif.last_error is None
    assert notif.last_used_at is not None


@pytest.mark.asyncio
async def test_records_last_status_on_failure(
    webhook_stub: FakeWebhook,
) -> None:
    notif = _notification()
    failing_apprise = FakeApprise(
        calls=[],
        result=AppriseSendResult(
            success=False, error_message="apprise unreachable"
        ),
    )
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=failing_apprise,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert outcome.skip_reason is None  # delivery was attempted
    assert notif.last_status == "failed"
    assert notif.last_error == "apprise unreachable"
    assert notif.last_used_at is not None


@pytest.mark.asyncio
async def test_apprise_exception_recorded_as_failure(
    webhook_stub: FakeWebhook,
) -> None:
    """Unexpected transport exceptions are caught so one bad
    target doesn't crash the dispatcher loop. The audit row
    captures the exception class + message."""

    async def boom(**kwargs: Any) -> AppriseSendResult:
        raise RuntimeError("boom")

    notif = _notification()
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=boom,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert notif.last_status == "failed"
    assert "RuntimeError" in (notif.last_error or "")


# ---------------------------------------------------------------------------
# Webhook routing — json://-scheme notifications use the Sonarr builder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_scheme_routes_to_webhook_transport(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """A notification with ``apprise_url_scheme='json'`` (the
    Sonarr-format webhook target) bypasses Apprise and hits the
    webhook transport with a Sonarr-shaped dict body."""
    notif = _notification(apprise_url_scheme="json")
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True
    assert apprise_stub.calls == []
    assert len(webhook_stub.calls) == 1
    body = webhook_stub.calls[0][1]
    assert body["eventType"] == "Download"
    assert body["series"]["title"] == "Sonic the Hedgehog"


@pytest.mark.asyncio
async def test_jsons_scheme_also_routes_to_webhook(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification(apprise_url_scheme="jsons")
    outcome = await dispatch_to_notification(
        notification=notif,
        event=_import_event(),
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True
    assert webhook_stub.calls != []


# ---------------------------------------------------------------------------
# OnHealthIssue severity filtering — include_health_warnings/errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_warning_skipped_when_warnings_disabled(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """Warnings are noisy on busy systems; operators can opt out
    by toggling ``include_health_warnings = False`` while still
    receiving errors."""
    from romarr.notifications.types import (
        ComponentCategory,
        HealthStatus,
        OnHealthIssuePayload,
    )

    notif = _notification(include_health_warnings=False)
    event = OnHealthIssuePayload(
        component="indexer:X",
        category=ComponentCategory.INDEXER,
        severity="warning",
        previous_status=HealthStatus.OK,
        current_status=HealthStatus.WARNING,
        message="caps reachable, but slow",
    )
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is False
    assert outcome.skip_reason == "health_severity_filtered"


@pytest.mark.asyncio
async def test_event_with_no_game_skips_tag_filter(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    """Events without a ``game`` namespace (OnFail, OnDatUpdate,
    OnHealthIssue) bypass tag filtering — there's nothing to
    intersect against."""
    notif = _notification(tags=["family-friendly"])
    fail_event = OnFailPayload(
        release=_release(), error_msg="extract:bomb-detected"
    )
    outcome = await dispatch_to_notification(
        notification=notif,
        event=fail_event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True


@pytest.mark.asyncio
async def test_game_added_event_respects_game_tags(
    apprise_stub: FakeApprise, webhook_stub: FakeWebhook
) -> None:
    notif = _notification(tags=["family-friendly"])
    event = OnGameAddedPayload(
        game=_game(tags=("family-friendly",)), library_id=1
    )
    outcome = await dispatch_to_notification(
        notification=notif,
        event=event,
        send_apprise=apprise_stub,
        send_webhook=webhook_stub,
    )
    assert outcome.delivered is True


# ---------------------------------------------------------------------------
# DispatchOutcome — public dataclass shape
# ---------------------------------------------------------------------------


def test_dispatch_outcome_is_dataclass() -> None:
    """Sanity coverage: the public outcome carries the fields
    the channel/loop wires to audit logging."""
    outcome = DispatchOutcome(delivered=True, skip_reason=None)
    assert outcome.delivered is True
    assert outcome.skip_reason is None
