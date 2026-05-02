/**
 * WebSocket message taxonomy (T048, mirrors spec 013
 * `romarr.api.ws.messages.MessageType`).
 *
 * The 12 documented event types the /signalr/messages bridge
 * can emit. Adding a new type goes through the spec — pinning
 * the literal union here means a typo on either side breaks
 * the build instead of dropping silently.
 *
 * Envelope shape:
 *
 *     { "messageType": "<MessageType>", "data": <event-specific> }
 *
 * Plain JSON-over-WebSocket. Server-side ping every 30 s;
 * clients ping back. No replay on reconnect — the channel is a
 * live notification surface, not a queue. Clients that want to
 * resync re-fetch via the REST API (via TanStack Query
 * invalidation, see invalidations.ts).
 */

export const MESSAGE_TYPES = [
  // Task lifecycle (spec 012).
  "taskStarted",
  "taskProgress",
  "taskFinished",

  // Queue mirror (spec 005 + spec 013 queue_entry table).
  "queueUpdated",

  // Library mutations (spec 001).
  "gameAdded",
  "gameUpdated",
  "gameDeleted",

  // Release acquisition (spec 007 / spec 008).
  "releaseGrabbed",
  "releaseImported",
  "releaseFailed",

  // System-level (spec 011).
  "healthChanged",
  "systemMessage",
] as const;

export type MessageType = (typeof MESSAGE_TYPES)[number];

export interface WsEnvelope<T = unknown> {
  messageType: MessageType;
  data: T;
}

/** Connection lifecycle states tracked by the connection store. */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline";

export function isMessageType(value: string): value is MessageType {
  return (MESSAGE_TYPES as readonly string[]).includes(value);
}

export function isWsEnvelope(value: unknown): value is WsEnvelope {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as { messageType?: unknown; data?: unknown };
  return (
    typeof candidate.messageType === "string"
    && isMessageType(candidate.messageType)
    && typeof candidate.data === "object"
    && candidate.data !== null
  );
}
