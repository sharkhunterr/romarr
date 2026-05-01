"""Default-template render tests (T029)."""

from __future__ import annotations

import pytest

from romarr.notifications.models import Notification
from romarr.notifications.templates import render_event
from romarr.notifications.types import (
    ComponentCategory,
    DownloadClientRef,
    DumpRef,
    EventType,
    GameRef,
    HealthStatus,
    IndexerRef,
    OnDatUpdatePayload,
    OnFailPayload,
    OnGameAddedPayload,
    OnGrabPayload,
    OnHealthIssuePayload,
    OnImportPayload,
    OnUpgradePayload,
    ReleaseRef,
)


def _bare_notification() -> Notification:
    """A Notification with no per-event format overrides — every
    render falls back to the default template."""
    return Notification(
        name="test",
        apprise_url_encrypted=b"",
        apprise_url_scheme="discord",
    )


def _game() -> GameRef:
    return GameRef(
        id=1,
        title="Sonic the Hedgehog",
        platform_slug="megadrive",
        platform_name="Sega Mega Drive",
        igdb_id=42,
        tags=("platformer",),
    )


def _release() -> ReleaseRef:
    return ReleaseRef(
        id=10,
        name="Sonic the Hedgehog (USA)",
        region="USA",
        languages=("en",),
        revision=None,
        dump_status="verified",
        naming_convention="no-intro",
    )


def _dump(verified: bool = True) -> DumpRef:
    return DumpRef(
        path="/library/megadrive/Sonic.md",
        sha1="a" * 40,
        crc32="aabbccdd",
        size_bytes=524288,
        dat_verified=verified,
        dat_source="no-intro",
    )


# ---------------------------------------------------------------------------
# T029 — every default template renders against its payload
# ---------------------------------------------------------------------------


def test_on_grab_renders() -> None:
    payload = OnGrabPayload(
        game=_game(),
        release=_release(),
        indexer=IndexerRef(id=1, name="MyIndexer"),
        download_client=DownloadClientRef(
            id=1, name="qbit-local", type="qbittorrent"
        ),
        download_id="abc",
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out == (
        "🎯 Grabbed: Sonic the Hedgehog (USA) "
        "— Sonic the Hedgehog (USA) from MyIndexer"
    )


def test_on_import_renders_dat_verified() -> None:
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump(verified=True)
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out == (
        "✅ Imported: Sonic the Hedgehog "
        "(Sega Mega Drive, USA) — DAT ✓"
    )


def test_on_import_renders_dat_unverified() -> None:
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump(verified=False)
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert "DAT ?" in out


def test_on_upgrade_renders() -> None:
    new_release = ReleaseRef(id=20, name="Sonic the Hedgehog (USA, Rev A)")
    payload = OnUpgradePayload(
        game=_game(),
        old_release=_release(),
        new_release=new_release,
        new_dump=_dump(),
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert "Upgraded: Sonic the Hedgehog" in out
    assert "Sonic the Hedgehog (USA)" in out  # old name
    assert "Sonic the Hedgehog (USA, Rev A)" in out  # new name


def test_on_fail_renders() -> None:
    payload = OnFailPayload(
        release=_release(), error_msg="extract:bomb-detected"
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out == (
        "❌ Failed: Sonic the Hedgehog (USA) — extract:bomb-detected"
    )


@pytest.mark.parametrize(
    "severity,expected_prefix",
    [
        ("warning", "⚠️"),
        ("error", "🚨"),
        ("recovered", "✅"),
    ],
)
def test_on_health_issue_renders(
    severity: str, expected_prefix: str
) -> None:
    payload = OnHealthIssuePayload(
        component="indexer:MyIndexer",
        category=ComponentCategory.INDEXER,
        severity=severity,  # type: ignore[arg-type]
        previous_status=HealthStatus.OK,
        current_status=HealthStatus.WARNING,
        message="last poll returned 503",
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out.startswith(expected_prefix)
    assert "indexer:MyIndexer" in out
    assert "last poll returned 503" in out


def test_on_dat_update_renders() -> None:
    payload = OnDatUpdatePayload(
        source="no-intro",
        platform="megadrive",
        entries_count=1234,
        version="2026-04-30",
    )
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out == "📥 DAT updated: no-intro megadrive → 1234 entries"


def test_on_game_added_renders() -> None:
    payload = OnGameAddedPayload(game=_game(), library_id=1)
    out = render_event(notification=_bare_notification(), payload=payload)
    assert out == "➕ New game: Sonic the Hedgehog (Sega Mega Drive)"


# ---------------------------------------------------------------------------
# Operator override path
# ---------------------------------------------------------------------------


def test_operator_override_takes_precedence() -> None:
    """When the notification row carries an
    ``on_<event>_format`` override, the renderer uses it instead
    of the default."""
    notif = _bare_notification()
    notif.on_import_format = "Custom: {{ game.title }}!"
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump()
    )
    out = render_event(notification=notif, payload=payload)
    assert out == "Custom: Sonic the Hedgehog!"


def test_default_template_used_when_override_is_empty_string() -> None:
    """An empty-string override is treated as absent — the
    default template fires."""
    notif = _bare_notification()
    notif.on_import_format = ""
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump()
    )
    out = render_event(notification=notif, payload=payload)
    assert out.startswith("✅ Imported")


# ---------------------------------------------------------------------------
# Coverage check: every EventType has a default template
# ---------------------------------------------------------------------------


def test_every_event_type_has_a_default_template() -> None:
    from romarr.notifications.templates import DEFAULT_TEMPLATES

    for event_type in EventType:
        assert event_type in DEFAULT_TEMPLATES
