"""Sonarr v3 webhook envelope compatibility (T021-T023, FR-006a, SC-003).

The Sonarr v3 envelope's TV-domain keys are populated from
Romarr's Game/Release domain via a documented semantic remap
(see ``docs/api/notification/webhook-payloads.md``). These tests
lock the byte-for-byte shape against fixture JSON so a future
refactor cannot silently break Notifiarr / Homepage / Tautulli
consumers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from romarr.notifications.models import Notification
from romarr.notifications.templates import build_sonarr_webhook_body
from romarr.notifications.types import (
    DownloadClientRef,
    DumpRef,
    GameRef,
    IndexerRef,
    OnGrabPayload,
    OnImportPayload,
    OnUpgradePayload,
    ReleaseRef,
)

_FIXTURES = Path(__file__).parent / "sonarr_webhook_fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _bare_notification() -> Notification:
    return Notification(
        name="webhook",
        apprise_url_encrypted=b"",
        apprise_url_scheme="json",
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


def _dump() -> DumpRef:
    return DumpRef(
        path="/library/megadrive/Sonic.md",
        sha1="a" * 40,
        crc32="aabbccdd",
        size_bytes=524288,
        dat_verified=True,
        dat_source="no-intro",
    )


# ---------------------------------------------------------------------------
# T021 — OnGrab payload matches fixture
# ---------------------------------------------------------------------------


def test_grab_payload_matches_fixture() -> None:
    payload = OnGrabPayload(
        game=_game(),
        release=_release(),
        indexer=IndexerRef(id=1, name="MyIndexer"),
        download_client=DownloadClientRef(
            id=1, name="qbit-local", type="qbittorrent"
        ),
        download_id="abc123",
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    expected = _load_fixture("grab_payload.json")
    assert body == expected


# ---------------------------------------------------------------------------
# T022 — OnImport payload matches fixture (Sonarr calls it "Download")
# ---------------------------------------------------------------------------


def test_download_payload_matches_fixture() -> None:
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump(), is_upgrade=False
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    expected = _load_fixture("download_payload.json")
    assert body == expected


# ---------------------------------------------------------------------------
# T023 — OnUpgrade payload sets isUpgrade = True
# ---------------------------------------------------------------------------


def test_isupgrade_flag_true_for_upgrade_event() -> None:
    new_release = ReleaseRef(
        id=20,
        name="Sonic the Hedgehog (USA, Rev A)",
        region="USA",
        naming_convention="no-intro",
    )
    new_dump = DumpRef(
        path="/library/megadrive/Sonic-RevA.md",
        size_bytes=524288,
        dat_verified=True,
    )
    payload = OnUpgradePayload(
        game=_game(),
        old_release=_release(),
        new_release=new_release,
        new_dump=new_dump,
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    assert body["isUpgrade"] is True
    assert body["eventType"] == "Download"
    assert body["episodeFile"]["path"] == "/library/megadrive/Sonic-RevA.md"
    # The deletedFiles array carries the old dump's metadata so
    # consumers can show "replaced X with Y" UIs.
    assert isinstance(body["deletedFiles"], list)
    assert len(body["deletedFiles"]) == 1


def test_isupgrade_flag_false_for_fresh_import() -> None:
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump(), is_upgrade=False
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    assert body["isUpgrade"] is False


# ---------------------------------------------------------------------------
# FR-006a — empty fields emit as 0/"" never omitted
# ---------------------------------------------------------------------------


def test_missing_igdb_id_emits_as_zero() -> None:
    """``series.tvdbId`` is a non-null int in Sonarr's schema —
    NULL ``igdb_id`` must fall back to ``0`` (FR-006a)."""
    game = GameRef(
        id=1,
        title="Untitled Hack",
        platform_slug="megadrive",
        platform_name="Sega Mega Drive",
        igdb_id=None,
    )
    payload = OnImportPayload(
        game=game, release=_release(), dump=_dump()
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    assert body["series"]["tvdbId"] == 0
    # And the field is present, not omitted.
    assert "tvdbId" in body["series"]


def test_empty_string_keys_present_never_omitted() -> None:
    payload = OnImportPayload(
        game=_game(), release=_release(), dump=_dump()
    )
    body = build_sonarr_webhook_body(
        payload=payload, notification=_bare_notification()
    )
    # ``series.path`` has no plumbing yet — emits "" not None.
    assert body["series"]["path"] == ""
    assert body["series"]["imdbId"] == ""
    assert body["episodeFile"]["sceneName"] == ""
    assert body["episodeFile"]["releaseGroup"] == ""


# ---------------------------------------------------------------------------
# Coverage check: every event type produces a body the schema sees as a dict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        OnGrabPayload(
            game=_game(),
            release=_release(),
            indexer=IndexerRef(id=1, name="X"),
            download_client=DownloadClientRef(id=1, name="X", type="qbittorrent"),
            download_id="x",
        ),
        OnImportPayload(game=_game(), release=_release(), dump=_dump()),
        OnUpgradePayload(
            game=_game(),
            old_release=_release(),
            new_release=_release(),
            new_dump=_dump(),
        ),
    ],
)
def test_event_type_field_always_set(payload: object) -> None:
    body = build_sonarr_webhook_body(
        payload=payload,  # type: ignore[arg-type]
        notification=_bare_notification(),
    )
    assert isinstance(body, dict)
    assert "eventType" in body
    assert isinstance(body["eventType"], str)
    assert body["instanceName"] == "Romarr"
