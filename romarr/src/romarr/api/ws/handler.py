"""FastAPI WebSocket route at /signalr/messages (T073, FR-018).

Lifecycle of a single connection:

  1. Client opens WS to ``/signalr/messages``.
  2. Server resolves the principal via
     :func:`romarr.api.ws.auth.authenticate_upgrade`.
     - On success: ``websocket.accept()``; subscription added
       to the registry; an opening ``systemMessage`` welcome
       envelope is sent so the client can confirm the channel
       is live.
     - On failure: ``websocket.close(code=1008)`` (policy
       violation, mirrors HTTP 401 for FR-018).
  3. Server enters a receive loop. Any message from the client
     is treated as a keepalive ping; the server echoes a
     ``systemMessage`` pong back. Clients SHOULD ping every 30 s;
     the server itself doesn't kick idle connections in this
     slice (the asyncio.timeout guard lands with the
     full-protocol slice when the bridge ships).
  4. On any disconnect (clean close, network drop, exception),
     the registry entry is removed and the loop exits.

The handler is mounted under the FastAPI app rather than the
``/api/v3`` prefix because the SignalR-compat path is
``/signalr/messages`` (no ``/api/v3`` prefix per Sonarr's
contract).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.ws.auth import authenticate_upgrade
from romarr.api.ws.messages import MessageType, build_envelope
from romarr.api.ws.subscriptions import (
    Subscription,
    SubscriptionRegistry,
)

router = APIRouter(tags=["WebSocket"])


async def _get_ws_db(
    websocket: WebSocket,
) -> AsyncIterator[AsyncSession]:
    """WS-scoped variant of ``get_db``. The HTTP version takes
    a ``Request`` (FastAPI's request-scoped injection); the WS
    version takes a ``WebSocket`` because there's no Request in
    play. Both pull the same sessionmaker off ``app.state``.

    The session is opened on accept and closed on disconnect —
    matches the connection lifetime, NOT a per-message scope."""
    sessionmaker = websocket.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield session


def _get_registry(websocket: WebSocket) -> SubscriptionRegistry:
    """Pull the per-app :class:`SubscriptionRegistry` off
    ``app.state``. The factory creates one at startup; tests
    that exercise WS routes directly stamp their own."""
    registry: SubscriptionRegistry | None = getattr(
        websocket.app.state, "ws_subscriptions", None
    )
    if registry is None:
        registry = SubscriptionRegistry()
        websocket.app.state.ws_subscriptions = registry
    return registry


@router.websocket("/signalr/messages")
async def signalr_messages(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(_get_ws_db)],
) -> None:
    """The single push-channel WebSocket route. Clients open it
    once and keep it alive for the lifetime of the operator UI
    session."""
    principal = await authenticate_upgrade(websocket, session=session)
    if principal is None:
        # Policy violation — same intent as HTTP 401 for the REST
        # surface. The connection MUST be rejected before
        # ``accept`` so the client sees the upgrade failure.
        await websocket.close(code=1008, reason="unauthenticated")
        return

    await websocket.accept()

    registry = _get_registry(websocket)
    subscription: Subscription = await registry.add(websocket, principal)

    # Welcome message — confirms the channel is live and gives
    # the client its connection id (echoed back on every server
    # event under ``data.connectionId`` once the bridge ships).
    await websocket.send_json(
        build_envelope(
            MessageType.SYSTEM_MESSAGE,
            {
                "kind": "welcome",
                "connectionId": subscription.connection_id,
                "username": principal.username,
            },
        )
    )

    try:
        while True:
            # Receive — Starlette decodes JSON if the frame is
            # text. We treat any received frame as a ping.
            await websocket.receive_text()
            if websocket.application_state != WebSocketState.CONNECTED:
                break
            await websocket.send_json(
                build_envelope(
                    MessageType.SYSTEM_MESSAGE,
                    {"kind": "pong"},
                )
            )
    except WebSocketDisconnect:
        # Clean disconnect — fall through to cleanup.
        pass
    finally:
        await registry.remove(subscription.connection_id)


__all__ = ["router"]
