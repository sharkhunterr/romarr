"""WS lossy-channel contract tests (T067, FR-019).

Spec 013 mandates: the WS is a live notification channel, NOT
a queue. A client that disconnects mid-event misses it; on
reconnect, the server does NOT replay the missed events.
Clients that want missed events re-fetch via the REST API.

This is the registry's "no buffer" property — any future slice
that adds a per-user replay buffer would invalidate this test.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from romarr.api.ws import MessageType, SubscriptionRegistry, build_envelope


def _broadcast(client: TestClient, payload: dict) -> None:
    registry: SubscriptionRegistry = (
        client.app.state.ws_subscriptions  # type: ignore[attr-defined]
    )
    asyncio.run(registry.broadcast(payload))


def test_disconnected_client_does_not_replay_on_reconnect(
    authed_ws_client: tuple[TestClient, str],
) -> None:
    """Open WS A → broadcast E1 (A receives) → disconnect A →
    open WS B → assert B does NOT see E1 → broadcast E2 → B
    receives E2. Pins FR-019 — no replay."""
    client, plaintext = authed_ws_client

    e1 = build_envelope(
        MessageType.SYSTEM_MESSAGE, {"kind": "info", "text": "first"}
    )
    e2 = build_envelope(
        MessageType.SYSTEM_MESSAGE, {"kind": "info", "text": "second"}
    )

    # Open A, broadcast E1, A receives it, then close A.
    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws_a:
        ws_a.receive_json()  # welcome
        _broadcast(client, e1)
        first = ws_a.receive_json()
        assert first["data"]["text"] == "first"
    # A is now disconnected — context manager exited.

    # B reconnects fresh.
    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws_b:
        welcome = ws_b.receive_json()
        assert welcome["data"]["kind"] == "welcome"
        # No replay of E1 — the next frame B sees is E2.
        _broadcast(client, e2)
        second = ws_b.receive_json()
        assert second["data"]["text"] == "second"


def test_disconnect_removes_subscription_from_registry(
    authed_ws_client: tuple[TestClient, str],
) -> None:
    """Defensive — confirms the handler's `finally` cleanup
    actually fires. Otherwise the registry would leak
    subscriptions across disconnects, and a future broadcast
    would try to send to a dead WebSocket (broadcast catches
    the exception, but the count stays inflated)."""
    client, plaintext = authed_ws_client
    registry: SubscriptionRegistry = (
        client.app.state.ws_subscriptions  # type: ignore[attr-defined]
    )

    assert len(registry) == 0
    with client.websocket_connect(
        f"/signalr/messages?apikey={plaintext}"
    ) as ws:
        ws.receive_json()  # welcome
        assert len(registry) == 1
    # Exiting the WS context closes the connection. Give the
    # handler's finally block a beat to remove the entry.
    for _ in range(10):
        if len(registry) == 0:
            break
        # Yield the loop briefly — the cleanup happens in the
        # WS handler's coroutine which is being torn down by
        # Starlette's TestClient asynchronously.
        import time

        time.sleep(0.01)
    assert len(registry) == 0
