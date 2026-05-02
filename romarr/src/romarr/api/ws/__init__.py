"""WebSocket subsystem (spec 013, US4 / FR-018-019).

The /signalr/messages WebSocket is Romarr's push channel for
operator-UI live updates: queue progress, task transitions,
health changes, system messages. The path mirrors Sonarr's
/signalr/messages so existing client tooling that hard-codes
the route works unchanged; the wire format is plain
JSON-over-WebSocket with SignalR-shaped envelopes
(``{messageType, data}``) rather than the SignalR negotiate /
hub-method protocol — the constitutional "SignalR-compat"
mandate refers to the path and event taxonomy, not the wire
protocol (see spec 013 Q2 clarification).

Submodules:
  * :mod:`romarr.api.ws.messages`       — MessageType StrEnum
    and the canonical envelope shape;
  * :mod:`romarr.api.ws.auth`           — on-upgrade auth
    resolver (cookie / apikey query / bearer header) — reuses
    spec 010's auth chain;
  * :mod:`romarr.api.ws.subscriptions`  — in-memory
    subscriber registry keyed by connection id; tear down
    on disconnect;
  * :mod:`romarr.api.ws.handler`        — the FastAPI
    WebSocket route at /signalr/messages.

The bridge (consumes spec 011's pub/sub channel and forwards
events to subscribers) lands in a follow-up slice when the
spec 011 pub/sub surface is exposed; today the foundation
ships handler + auth + registry so the WS upgrade flow works
end-to-end.
"""

from romarr.api.ws.handler import router as ws_router
from romarr.api.ws.messages import MessageType, build_envelope
from romarr.api.ws.subscriptions import SubscriptionRegistry

__all__ = [
    "MessageType",
    "SubscriptionRegistry",
    "build_envelope",
    "ws_router",
]
