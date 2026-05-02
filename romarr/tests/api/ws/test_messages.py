"""WS message-coverage tests (T066, FR-018, SC-004).

Drives `SubscriptionRegistry.broadcast()` directly with each of
the 12 documented `MessageType` values and asserts the
connected client receives the canonical envelope shape.

The bridge that wires spec 011's pub/sub channel to this
broadcast call lands in T072; this slice pins the contract
between the broadcast surface and the WS handler so the bridge
slice can ship by just calling broadcast.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from romarr.api.ws import MessageType, SubscriptionRegistry, build_envelope


def _broadcast(
    client: TestClient,
    message_type: MessageType,
    data: dict[str, Any],
) -> None:
    """Trigger a broadcast on the app's registry. Runs the
    coroutine inside the TestClient's event loop via
    ``client.app.state.ws_subscriptions.broadcast``."""
    registry: SubscriptionRegistry = (
        client.app.state.ws_subscriptions  # type: ignore[attr-defined]
    )
    asyncio.run(registry.broadcast(build_envelope(message_type, data)))


# ---------------------------------------------------------------------------
# T066 — table-driven over the 12 documented MessageType values
# ---------------------------------------------------------------------------


_SAMPLE_PAYLOADS: dict[MessageType, dict[str, Any]] = {
    MessageType.TASK_STARTED: {"id": 7, "name": "MissingSearch"},
    MessageType.TASK_PROGRESS: {"id": 7, "elapsed_steps": 12},
    MessageType.TASK_FINISHED: {"id": 7, "status": "success"},
    MessageType.QUEUE_UPDATED: {"id": 42, "progress": 0.5},
    MessageType.GAME_ADDED: {"id": 100, "title": "Sonic"},
    MessageType.GAME_UPDATED: {"id": 100, "monitored": True},
    MessageType.GAME_DELETED: {"id": 100},
    MessageType.RELEASE_GRABBED: {"id": 200, "indexer": "Prowlarr"},
    MessageType.RELEASE_IMPORTED: {"id": 200, "destination": "/library/foo"},
    MessageType.RELEASE_FAILED: {"id": 200, "reason": "checksum_mismatch"},
    MessageType.HEALTH_CHANGED: {"check": "diskFree", "status": "warn"},
    MessageType.SYSTEM_MESSAGE: {"kind": "info", "text": "boot complete"},
}


@pytest.mark.parametrize(
    "message_type",
    list(MessageType),
    ids=[mt.value for mt in MessageType],
)
def test_each_message_type_round_trips_to_subscriber(
    authed_ws_client: tuple[TestClient, str],
    message_type: MessageType,
) -> None:
    """Each MessageType value, broadcast through the registry,
    materialises in the connected client as a canonical
    `{messageType, data}` envelope."""
    client, plaintext = authed_ws_client
    payload = _SAMPLE_PAYLOADS[message_type]

    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws:
        ws.receive_json()  # consume welcome envelope

        _broadcast(client, message_type, payload)

        envelope = ws.receive_json()
        assert envelope["messageType"] == message_type.value
        assert envelope["data"] == payload


def test_all_12_documented_types_are_covered() -> None:
    """SC-004 sanity: the parametrize table maps every value in
    the StrEnum, no drift between the spec and the test."""
    assert set(MessageType) == set(_SAMPLE_PAYLOADS.keys())
    assert len(MessageType) == 12


# ---------------------------------------------------------------------------
# Multi-subscriber broadcast
# ---------------------------------------------------------------------------


def test_broadcast_reaches_every_subscriber(
    authed_ws_client: tuple[TestClient, str],
) -> None:
    """Two concurrent connections from the same operator both
    receive a broadcast. Mirrors the operator-with-two-tabs
    case the registry's per-connection-UUID keying is designed
    for."""
    client, plaintext = authed_ws_client

    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws_a, client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws_b:
        ws_a.receive_json()  # consume welcomes
        ws_b.receive_json()

        _broadcast(
            client,
            MessageType.SYSTEM_MESSAGE,
            {"kind": "info", "text": "to-everyone"},
        )

        envelope_a = ws_a.receive_json()
        envelope_b = ws_b.receive_json()
        assert envelope_a == envelope_b
        assert envelope_a["data"]["text"] == "to-everyone"
