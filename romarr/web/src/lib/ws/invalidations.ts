/**
 * Event → query-key invalidation mapping (T049).
 *
 * Pure function — no side effects, no QueryClient reference.
 * The bridge in `useWebSocketBridge` consumes the keys and
 * calls `queryClient.invalidateQueries({ queryKey: ... })`.
 *
 * Per the spec 013 invariant, the WebSocket is a NOTIFICATION
 * channel, not a source of truth: every server event listed
 * here triggers a re-fetch of the impacted REST surface. The
 * payload is intentionally NOT trusted to mutate the cache
 * directly.
 */

import type { QueryKey } from "@tanstack/react-query";

import type { MessageType } from "./types";

export function eventToInvalidations(messageType: MessageType): QueryKey[] {
  switch (messageType) {
    // Task lifecycle — refresh the scheduler grid + history.
    case "taskStarted":
    case "taskProgress":
    case "taskFinished":
      return [["system", "tasks"], ["history"]];

    // Queue mirror — Activity tab live progress.
    case "queueUpdated":
      return [["queue"]];

    // Library mutations — every Game-driven query needs to
    // resync. The library/wanted/dashboard each carry their own
    // cache slot; invalidating the broad ["games"] root would
    // need to land once those queries exist.
    case "gameAdded":
    case "gameUpdated":
    case "gameDeleted":
      return [["games"], ["wanted"], ["library"]];

    // Release acquisition — Wanted + Activity history are the
    // two visible surfaces today; Game Detail Releases will
    // join once it ships.
    case "releaseGrabbed":
    case "releaseImported":
    case "releaseFailed":
      return [["wanted"], ["history"], ["queue"]];

    // System-level — Dashboard health panel.
    case "healthChanged":
      return [["system", "health"]];

    // System message (welcome / pong / generic) — no cache
    // impact. Toast surfacing lands with the i18n / Toaster
    // slice.
    case "systemMessage":
      return [];
  }
}
