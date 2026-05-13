/**
 * React bridge for the WebSocket client (T050, T073-toast).
 *
 * Lifecycle:
 *   1. Reads the current principal via `useCurrentPrincipal`.
 *   2. Boots a single `WebSocketClient` instance once the
 *      operator is authenticated.
 *   3. Wires the client's `onMessage` to:
 *        a. the QueryClient — every key returned by
 *           `eventToInvalidations` triggers a re-fetch.
 *        b. the toast viewport — `systemMessage` envelopes
 *           surface as info-level toasts (welcome / pong /
 *           generic). Pong is silenced.
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
import { useTranslation } from "react-i18next";

import { useCurrentPrincipal } from "@/lib/api/queries/auth";
import { useConnectionStore } from "@/lib/store/connection";
import { useToastStore } from "@/lib/store/toast";

import { WebSocketClient } from "./client";
import { eventToInvalidations } from "./invalidations";
import type { WsEnvelope } from "./types";

interface SystemMessageData {
  kind?: string;
  username?: string;
  [key: string]: unknown;
}

function isSystemMessage(env: WsEnvelope): env is WsEnvelope<SystemMessageData> {
  return env.messageType === "systemMessage";
}

export function useWebSocketBridge(): void {
  const { t } = useTranslation("common");
  const queryClient = useQueryClient();
  const principal = useCurrentPrincipal();
  const setStatus = useConnectionStore((state) => state.setStatus);

  // The bridge is gated on the principal being resolved; the
  // effect re-runs when auth flips so logout cleanly stops the
  // client and login starts a fresh one.
  const principalId = principal.data?.id ?? null;

  useEffect(() => {
    if (principalId === null) {
      setStatus("idle");
      return;
    }

    const client = new WebSocketClient({
      onMessage: (envelope) => {
        const keys = eventToInvalidations(envelope.messageType);
        for (const queryKey of keys) {
          void queryClient.invalidateQueries({ queryKey });
        }

        if (isSystemMessage(envelope)) {
          const kind = envelope.data.kind ?? "";
          if (kind === "pong" || kind === "welcome") {
            // ``pong`` is a server keepalive; ``welcome`` fires on
            // every (re)connect — the WS does that on every page
            // refresh, so a toast each time is pure noise. The
            // ConnectionIndicator pill already shows connection
            // state, so this stays silent.
            return;
          }
          if (kind === "" || kind === undefined) return;
          const title = t("toast.ws.generic", { kind });
          if (title.length === 0) return;
          useToastStore.getState().push({ kind: "info", title });
        }
      },
      onStatusChange: setStatus,
    });

    client.start();

    return () => {
      client.stop();
    };
  }, [principalId, queryClient, setStatus, t]);
}
