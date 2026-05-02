"""WebSocket message taxonomy (T069, FR-018, SC-004).

The 12 documented message types the bridge can emit. Adding a
new type goes through the spec — clients pin the StrEnum
values and a typo would break the contract silently otherwise.

Envelope shape per the spec 013 Q2 clarification:

    {
      "messageType": "<MessageType.value>",
      "data":        {<event-specific payload>}
    }

Plain JSON-over-WebSocket. Server-side ping every 30 s; clients
ping back. No replay on reconnect (FR-019) — the WS is a live
notification channel, not a queue. Clients that want missed
events re-fetch via the REST API.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    """The 12 documented WebSocket event types."""

    # Task lifecycle (spec 012).
    TASK_STARTED = "taskStarted"
    TASK_PROGRESS = "taskProgress"
    TASK_FINISHED = "taskFinished"

    # Queue mirror (spec 005 + spec 013 queue_entry table).
    QUEUE_UPDATED = "queueUpdated"

    # Library mutations (spec 001).
    GAME_ADDED = "gameAdded"
    GAME_UPDATED = "gameUpdated"
    GAME_DELETED = "gameDeleted"

    # Release acquisition (spec 007 / spec 008).
    RELEASE_GRABBED = "releaseGrabbed"
    RELEASE_IMPORTED = "releaseImported"
    RELEASE_FAILED = "releaseFailed"

    # System-level (spec 011).
    HEALTH_CHANGED = "healthChanged"
    SYSTEM_MESSAGE = "systemMessage"


def build_envelope(
    message_type: MessageType, data: dict[str, Any]
) -> dict[str, Any]:
    """Construct the canonical WS envelope. Returned dict is
    ready to be passed to ``websocket.send_json``."""
    return {"messageType": message_type.value, "data": data}


__all__ = ["MessageType", "build_envelope"]
