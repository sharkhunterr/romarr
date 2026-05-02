"""In-memory WebSocket subscription registry (T071, FR-019).

Keyed by a per-connection id (UUID4). Each entry tracks the
WebSocket object plus the resolved Principal so the bridge can
later filter events by user (e.g. user-scoped notifications).

Single-process — for multi-replica deployments the bridge
swaps to Redis pub/sub (same indirection pattern as the
idempotency cache).

The registry is intentionally lossy: there's no replay buffer.
A client that disconnects mid-event misses it and re-fetches via
the REST API on reconnect (FR-019). Trying to replay would mean
holding events in memory indefinitely or requiring the client to
prove its last-seen position — neither matches the operator's
"is the queue moving right now" intent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from fastapi import WebSocket

    from romarr.auth import Principal


@dataclass(frozen=True, slots=True)
class Subscription:
    """One live WebSocket connection."""

    connection_id: str
    websocket: WebSocket
    principal: Principal


class SubscriptionRegistry:
    """Process-local registry of live WS subscriptions.

    The registry is async-safe — adds and removes happen under
    a single :class:`asyncio.Lock` so the bridge's iteration
    can't see a half-mutated state. Iteration takes a snapshot
    so the broadcast loop can fire with the lock released."""

    def __init__(self) -> None:
        self._subs: dict[str, Subscription] = {}
        self._lock = asyncio.Lock()

    async def add(
        self, websocket: WebSocket, principal: Principal
    ) -> Subscription:
        sub = Subscription(
            connection_id=str(uuid4()),
            websocket=websocket,
            principal=principal,
        )
        async with self._lock:
            self._subs[sub.connection_id] = sub
        return sub

    async def remove(self, connection_id: str) -> None:
        async with self._lock:
            self._subs.pop(connection_id, None)

    async def snapshot(self) -> list[Subscription]:
        """Return a list of currently-active subscriptions —
        the caller can iterate with the lock released."""
        async with self._lock:
            return list(self._subs.values())

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Send ``payload`` (the canonical envelope) to every
        subscriber. Returns the count of successful sends.
        Failed sends (e.g. closed sockets) are logged
        implicitly via the websocket exception bubbling up
        from ``send_json`` — the bridge's caller decides
        whether to remove the sub.

        For now we swallow per-send errors so one dead
        connection doesn't abort the broadcast for the rest."""
        sent = 0
        for sub in await self.snapshot():
            try:
                await sub.websocket.send_json(payload)
                sent += 1
            except Exception:
                # The connection is dead; the handler's
                # disconnect cleanup will remove it.
                continue
        return sent

    def __len__(self) -> int:
        return len(self._subs)


__all__ = ["Subscription", "SubscriptionRegistry"]
