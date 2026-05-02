/**
 * Toast notification store (slice 73).
 *
 * Used for ephemeral feedback: WS systemMessage events,
 * mutation results (Backup queued / failed), background-job
 * outcomes. Toasts auto-dismiss after `durationMs` (default
 * 5 s; pass `0` to make it sticky).
 *
 * The viewport (`<ToastViewport />`) is mounted once from
 * AppLayout. Anywhere in the SPA can call
 * `useToastStore.getState().push({...})` to surface a toast —
 * no provider needed.
 */

import { create } from "zustand";

export type ToastKind = "info" | "success" | "warning" | "error";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
  /** Auto-dismiss timeout in ms. 0 keeps it sticky. */
  durationMs: number;
}

export interface PushToastInput {
  kind?: ToastKind;
  title: string;
  description?: string;
  durationMs?: number;
}

interface ToastState {
  toasts: Toast[];
  push: (input: PushToastInput) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const DEFAULT_DURATION_MS = 5000;
let counter = 0;

function nextId(): string {
  counter += 1;
  return `t-${Date.now()}-${counter}`;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (input) => {
    const id = nextId();
    const toast: Toast = {
      id,
      kind: input.kind ?? "info",
      title: input.title,
      ...(input.description !== undefined
        ? { description: input.description }
        : {}),
      durationMs: input.durationMs ?? DEFAULT_DURATION_MS,
    };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    return id;
  },
  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));
