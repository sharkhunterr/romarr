"""WebSocket bridge — spec 011 events → ``MessageType`` envelopes.

The notifications subsystem (spec 011) publishes ``BaseModel`` event
payloads on its in-process :class:`EventChannel`. The WebSocket
bridge (this module — T068 + T072) is a *global subscriber* on
that channel: every event also gets fanned out to live operator
WebSocket sessions as a canonical envelope:

    { "messageType": "<MessageType>", "data": { … } }

The mapping ``EventType → MessageType`` is fixed:

    OnGrab          → releaseGrabbed
    OnImport        → releaseImported
    OnUpgrade       → releaseImported   (an upgrade IS an import)
    OnFail          → releaseFailed
    OnHealthIssue   → healthChanged
    OnGameAdded     → gameAdded
    OnDatUpdate     → systemMessage     (no dedicated MessageType)

Unknown event types are skipped silently (forward-compat — a new
spec 011 event won't crash the bridge until its mapping lands).
The bridge is **best-effort**: a failed broadcast is logged but
never propagates back into the channel's publish loop.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from romarr.api.ws.messages import MessageType
from romarr.api.ws.subscriptions import SubscriptionRegistry
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import EventType

_logger = logging.getLogger(__name__)


_EVENT_TYPE_TO_MESSAGE: dict[EventType, MessageType] = {
    EventType.ON_GRAB: MessageType.RELEASE_GRABBED,
    EventType.ON_IMPORT: MessageType.RELEASE_IMPORTED,
    EventType.ON_UPGRADE: MessageType.RELEASE_IMPORTED,
    EventType.ON_FAIL: MessageType.RELEASE_FAILED,
    EventType.ON_HEALTH_ISSUE: MessageType.HEALTH_CHANGED,
    EventType.ON_GAME_ADDED: MessageType.GAME_ADDED,
    EventType.ON_DAT_UPDATE: MessageType.SYSTEM_MESSAGE,
}


class WsBridge:
    """Global subscriber that adapts spec 011 events into WS
    envelopes broadcast through :class:`SubscriptionRegistry`.

    Wire it once at app startup:

        bridge = WsBridge(registry=app.state.ws_subscriptions)
        bridge.attach(app.state.event_channel)

    The ``attach`` call is idempotent — subscribing the same
    instance twice is a no-op (the channel's ``subscribe_global``
    de-dups on identity).
    """

    def __init__(self, registry: SubscriptionRegistry) -> None:
        self._registry = registry

    async def emit_message(
        self, message_type: MessageType, data: Any | None = None
    ) -> None:
        """Direct broadcast of a non-spec-011 envelope.

        Used by producers that don't have a spec 011 ``EventType``
        equivalent — the queue reconciler (``QUEUE_UPDATED``), the
        scheduler (``TASK_STARTED`` / ``TASK_PROGRESS`` /
        ``TASK_FINISHED``), or routes that mutate observable state
        and want a live signal pushed to operator sessions.

        Best-effort: a failed broadcast is logged but never
        re-raises. Pass ``data=None`` for envelopes that don't need
        a payload (the receiver re-fetches via REST).
        """
        envelope = {"messageType": message_type.value, "data": data or {}}
        try:
            await self._registry.broadcast(envelope)
        except Exception:
            _logger.exception(
                "ws bridge raw broadcast failed; envelope dropped"
            )

    async def emit_event(self, event: Any) -> None:
        """Convert ``event`` to an envelope and broadcast.

        Public for direct producer use (the spec 008 importer's
        :class:`ImporterEventBus` can call this directly when it
        prefers to bypass the channel; it produces the same
        observable shape downstream).
        """
        if not isinstance(event, BaseModel):
            return  # not a spec 011 payload — nothing to map

        et = getattr(event, "event_type", None)
        if et is None:
            return

        try:
            event_type = EventType(et) if isinstance(et, str) else et
        except ValueError:
            return  # unknown event type, skip

        message_type = _EVENT_TYPE_TO_MESSAGE.get(event_type)
        if message_type is None:
            return  # event type without a dedicated WS surface

        envelope = {
            "messageType": message_type.value,
            "data": event.model_dump(mode="json"),
        }
        try:
            await self._registry.broadcast(envelope)
        except Exception:
            _logger.exception(
                "ws bridge broadcast failed; envelope dropped"
            )

    def attach(self, channel: EventChannel) -> None:
        """Subscribe globally to the given event channel."""
        channel.subscribe_global(self.emit_event)

    def detach(self, channel: EventChannel) -> None:
        """Unsubscribe (used in test cleanup)."""
        channel.unsubscribe_global(self.emit_event)


__all__ = ["WsBridge"]
