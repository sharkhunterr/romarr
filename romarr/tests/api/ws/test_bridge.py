"""WsBridge tests (slice 274 — spec 013 T068 + T072).

Verifies the documented contract: spec 011 events published on
the in-process :class:`EventChannel` are translated into
``MessageType`` envelopes and broadcast via
:class:`SubscriptionRegistry`.

The bridge is exercised end-to-end through the channel's
``publish`` API — that's the integration shape the importer /
search engine / scheduler all sit behind. The
``SubscriptionRegistry`` is replaced with a stand-in that
captures broadcasts so we don't need a real WebSocket.
"""

from __future__ import annotations

from typing import Any

import pytest

from romarr.api.ws.bridge import WsBridge
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import (
    DownloadClientRef,
    DumpRef,
    EventType,
    GameRef,
    HealthStatus,
    IndexerRef,
    OnFailPayload,
    OnGameAddedPayload,
    OnGrabPayload,
    OnHealthIssuePayload,
    OnImportPayload,
    OnUpgradePayload,
    ReleaseRef,
)


class _CapturingRegistry:
    """Stand-in for ``SubscriptionRegistry`` that records every
    envelope passed to ``broadcast``. The real registry returns
    an int (count of successful sends); we mirror that contract.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def broadcast(self, payload: dict[str, Any]) -> int:
        self.calls.append(payload)
        return len(payload)


def _game_ref() -> GameRef:
    return GameRef(
        id=1,
        title="Sonic the Hedgehog",
        platform_slug="megadrive",
        platform_name="Mega Drive",
    )


def _release_ref() -> ReleaseRef:
    return ReleaseRef(
        id=10,
        name="Sonic the Hedgehog (USA).md",
        region="USA",
        languages=("en",),
    )


def _indexer_ref() -> IndexerRef:
    return IndexerRef(id=1, name="indexer-1")


def _client_ref() -> DownloadClientRef:
    return DownloadClientRef(id=1, name="qbit", type="qbittorrent")


def _dump_ref() -> DumpRef:
    return DumpRef(path="/tmp/sonic.md", sha1="a" * 40)


@pytest.mark.asyncio
async def test_bridge_translates_on_grab_to_release_grabbed() -> None:
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    payload = OnGrabPayload(
        game=_game_ref(),
        release=_release_ref(),
        indexer=_indexer_ref(),
        download_client=_client_ref(),
        download_id="abc123",
        custom_format_score=120,
    )
    await channel.publish(payload)

    assert len(registry.calls) == 1
    assert registry.calls[0]["messageType"] == "releaseGrabbed"
    assert registry.calls[0]["data"]["event_type"] == "OnGrab"


@pytest.mark.asyncio
async def test_bridge_translates_on_import_to_release_imported() -> None:
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    await channel.publish(
        OnImportPayload(
            game=_game_ref(),
            release=_release_ref(),
            dump=_dump_ref(),
            is_upgrade=False,
        )
    )
    assert registry.calls[0]["messageType"] == "releaseImported"


@pytest.mark.asyncio
async def test_bridge_translates_on_upgrade_to_release_imported() -> None:
    """OnUpgrade ALSO maps to releaseImported — an upgrade is
    structurally an import (FR-018). The frontend doesn't need a
    separate ``releaseUpgraded`` MessageType; the ``is_upgrade``
    flag rides through in ``data``.
    """
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    await channel.publish(
        OnUpgradePayload(
            game=_game_ref(),
            old_release=_release_ref(),
            new_release=_release_ref(),
            new_dump=_dump_ref(),
        )
    )
    assert registry.calls[0]["messageType"] == "releaseImported"
    assert registry.calls[0]["data"]["event_type"] == "OnUpgrade"


@pytest.mark.asyncio
async def test_bridge_translates_on_fail_to_release_failed() -> None:
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    await channel.publish(
        OnFailPayload(
            release=_release_ref(),
            error_msg="connection refused",
            download_client=_client_ref(),
        )
    )
    assert registry.calls[0]["messageType"] == "releaseFailed"


@pytest.mark.asyncio
async def test_bridge_translates_health_issue_to_health_changed() -> None:
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    await channel.publish(
        OnHealthIssuePayload(
            component="indexer-1",
            category="indexer",
            severity="warning",
            previous_status=HealthStatus.OK,
            current_status=HealthStatus.WARNING,
            message="Indexer rate-limit exceeded",
        )
    )
    assert registry.calls[0]["messageType"] == "healthChanged"


@pytest.mark.asyncio
async def test_bridge_translates_game_added() -> None:
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    await channel.publish(OnGameAddedPayload(game=_game_ref()))
    assert registry.calls[0]["messageType"] == "gameAdded"


@pytest.mark.asyncio
async def test_bridge_skips_unknown_objects() -> None:
    """Non-spec-011 objects passed through publish are silently
    skipped — the bridge only acts on objects with an
    ``event_type`` field that maps to a known ``EventType``."""
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)

    # A plain dict — not a BaseModel — should be ignored.
    await channel.publish({"foo": "bar"})

    assert registry.calls == []


@pytest.mark.asyncio
async def test_detach_stops_broadcasts() -> None:
    """``detach`` removes the global subscription so future
    publishes don't reach the registry."""
    registry = _CapturingRegistry()
    bridge = WsBridge(registry=registry)  # type: ignore[arg-type]
    channel = EventChannel()
    bridge.attach(channel)
    bridge.detach(channel)

    await channel.publish(OnGameAddedPayload(game=_game_ref()))
    assert registry.calls == []
