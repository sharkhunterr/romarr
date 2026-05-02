/**
 * Connection-status store (T048 + spec 014 FR-019).
 *
 * Single source of truth for the WebSocket health signal the
 * UI surfaces (Header indicator, future toast on long-offline).
 * Updated by `useWebSocketBridge` as the client transitions;
 * read by anything that wants to react.
 *
 * Plain Zustand — no persist; the status is a runtime flag,
 * not a preference.
 */

import { create } from "zustand";

import type { ConnectionStatus } from "@/lib/ws/types";

interface ConnectionState {
  status: ConnectionStatus;
  /** Timestamp of the last status transition (ms epoch). */
  since: number;
  setStatus: (next: ConnectionStatus) => void;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  status: "idle",
  since: Date.now(),
  setStatus: (next) =>
    set((prev) =>
      prev.status === next
        ? prev
        : { status: next, since: Date.now(), setStatus: prev.setStatus },
    ),
}));
