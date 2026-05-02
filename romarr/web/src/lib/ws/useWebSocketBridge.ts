/**
 * React bridge for the WebSocket client (T050).
 *
 * Lifecycle:
 *   1. Reads the current principal via `useCurrentPrincipal`.
 *   2. Boots a single `WebSocketClient` instance once the
 *      operator is authenticated.
 *   3. Wires the client's `onMessage` to the QueryClient: every
 *      key returned by `eventToInvalidations` triggers a
 *      re-fetch.
 *   4. Wires the client's `onStatusChange` to the Zustand
 *      connection store.
 *   5. On unauth (logout, principal cleared), shuts the client
 *      down — auth is the only gate; the WS is useless without
 *      a session cookie.
 *
 * The bridge is mounted by the AppLayout (always present once
 * the operator clears the AuthGuard), so it boots on first
 * authenticated render and survives every page navigation.
 *
 * Each session creates one client. StrictMode's double-effect
 * is handled by the cleanup tearing the client down before the
 * second mount opens a new one.
 */

import { useEffect } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { useCurrentPrincipal } from "@/lib/api/queries/auth";
import { useConnectionStore } from "@/lib/store/connection";

import { WebSocketClient } from "./client";
import { eventToInvalidations } from "./invalidations";

export function useWebSocketBridge(): void {
  const queryClient = useQueryClient();
  const principal = useCurrentPrincipal();
  const setStatus = useConnectionStore((state) => state.setStatus);

  // The bridge is gated on the principal being resolved; the
  // effect re-runs when auth flips so logout cleanly stops the
  // client and login starts a fresh one.
  const principalId = principal.data?.id ?? null;

  useEffect(() => {
    if (principalId === null) {
      // Not authenticated — make sure any prior client is down
      // and the status reads "idle".
      setStatus("idle");
      return;
    }

    const client = new WebSocketClient({
      onMessage: (envelope) => {
        const keys = eventToInvalidations(envelope.messageType);
        for (const queryKey of keys) {
          void queryClient.invalidateQueries({ queryKey });
        }
      },
      onStatusChange: setStatus,
    });

    client.start();

    return () => {
      client.stop();
    };
  }, [principalId, queryClient, setStatus]);
}
