/**
 * PWA install-prompt plumbing (T056).
 *
 * Browsers that support add-to-homescreen fire a
 * `beforeinstallprompt` event when the install criteria are
 * satisfied (manifest + SW + engagement heuristic). We capture
 * the event globally so any UI surface (Header button, Settings
 * panel, dashboard banner) can trigger the prompt on demand.
 *
 * The plumbing is split:
 *   * `installPromptStore` — Zustand store carrying the
 *     deferred event + a "promptable" flag.
 *   * `useInstallPrompt()` — convenience hook that returns
 *     `{ canInstall, promptInstall }`.
 *
 * The deferred event is single-use: once the operator picks
 * accept or dismiss, the browser invalidates it and won't
 * re-fire `beforeinstallprompt` for that session.
 */

import { useCallback } from "react";

import { create } from "zustand";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

interface InstallState {
  event: BeforeInstallPromptEvent | null;
  isInstalled: boolean;
  setEvent: (event: BeforeInstallPromptEvent | null) => void;
  setInstalled: (installed: boolean) => void;
}

export const useInstallStore = create<InstallState>((set) => ({
  event: null,
  isInstalled: false,
  setEvent: (event) => set({ event }),
  setInstalled: (installed) => set({ isInstalled: installed }),
}));

let listenersBound = false;

export function bindInstallListeners(): void {
  if (listenersBound || typeof window === "undefined") {
    return;
  }
  listenersBound = true;

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    useInstallStore.getState().setEvent(event as BeforeInstallPromptEvent);
  });

  window.addEventListener("appinstalled", () => {
    useInstallStore.setState({ event: null, isInstalled: true });
  });

  // Already-installed (display-mode standalone or iOS).
  if (window.matchMedia("(display-mode: standalone)").matches) {
    useInstallStore.getState().setInstalled(true);
  }
}

export interface UseInstallPromptResult {
  canInstall: boolean;
  isInstalled: boolean;
  promptInstall: () => Promise<"accepted" | "dismissed" | "unavailable">;
}

export function useInstallPrompt(): UseInstallPromptResult {
  const event = useInstallStore((s) => s.event);
  const isInstalled = useInstallStore((s) => s.isInstalled);

  const promptInstall = useCallback(async () => {
    const current = useInstallStore.getState().event;
    if (current === null) {
      return "unavailable" as const;
    }
    await current.prompt();
    const choice = await current.userChoice;
    // The browser invalidates the event after the choice
    // resolves; clear it from the store so the UI doesn't keep
    // offering the prompt.
    useInstallStore.getState().setEvent(null);
    return choice.outcome;
  }, []);

  return {
    canInstall: event !== null && !isInstalled,
    isInstalled,
    promptInstall,
  };
}
