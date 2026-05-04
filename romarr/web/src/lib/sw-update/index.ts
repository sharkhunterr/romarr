/**
 * Service-worker update plumbing (CL001 + CL002 + CL003).
 *
 * Spec 014 FR-007a mandates the SW update lifecycle is opt-in: a
 * new build never silently swaps in. The plugin's ``registerType``
 * is set to ``"prompt"`` in ``vite.config.ts`` so vite-plugin-pwa
 * surfaces a callback when a waiting worker is detected; the user
 * has to click "Reload" before ``skipWaiting`` + ``clients.claim``
 * fire.
 *
 * The plumbing:
 *
 *   * ``useSwUpdateStore`` — Zustand store carrying the
 *     ``needsRefresh`` flag and the ``triggerUpdate`` callback the
 *     plugin hands us when the new SW becomes available.
 *   * ``registerServiceWorker`` — wraps the plugin's
 *     ``virtual:pwa-register`` import, lazy-loaded so test runs
 *     don't pull the virtual module.
 *   * ``dismissUpdate`` — operator dismissed the toast; the
 *     existing SW stays active and the prompt comes back next
 *     time the new SW reports.
 *
 * The store is the single source of truth; the toast component
 * subscribes to it. We don't wire the registration into a React
 * effect — registration must happen exactly once per page load,
 * before the React tree even renders, so the call lives in
 * ``main.tsx``.
 */

import { create } from "zustand";

type TriggerUpdate = (() => Promise<void>) | null;

interface SwUpdateState {
  needsRefresh: boolean;
  triggerUpdate: TriggerUpdate;
  setNeedsRefresh: (next: boolean, trigger: TriggerUpdate) => void;
  reset: () => void;
}

export const useSwUpdateStore = create<SwUpdateState>((set) => ({
  needsRefresh: false,
  triggerUpdate: null,
  setNeedsRefresh: (needsRefresh, triggerUpdate) =>
    set({ needsRefresh, triggerUpdate }),
  reset: () => set({ needsRefresh: false, triggerUpdate: null }),
}));

export async function applyUpdate(): Promise<void> {
  const trigger = useSwUpdateStore.getState().triggerUpdate;
  if (trigger === null) {
    return;
  }
  // The plugin's update() returns once the new SW has taken
  // control; we then reload so the page runs the new bundle.
  await trigger();
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}

export function dismissUpdate(): void {
  useSwUpdateStore.getState().reset();
}

interface RegisterSWModule {
  registerSW: (options: {
    onNeedRefresh?: () => void;
    onOfflineReady?: () => void;
  }) => (reloadPage?: boolean) => Promise<void>;
}

/**
 * Register the service worker via vite-plugin-pwa.
 *
 * Implementation detail: the ``virtual:pwa-register`` import is
 * indirected through a runtime-built string so Vite's import
 * analysis (and Vitest's resolver) can't statically reach it.
 * vite-plugin-pwa rewrites the specifier at build time when the
 * plugin is active; in test runs the dynamic import rejects and
 * the function silently no-ops.
 */
export async function registerServiceWorker(): Promise<void> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return;
  }
  // String concat hides the specifier from Vite's static
  // analyzer; the plugin still rewrites it at build time.
  const specifier = "virtual:" + "pwa-register";
  let mod: RegisterSWModule;
  try {
    mod = (await import(/* @vite-ignore */ specifier)) as RegisterSWModule;
  } catch {
    return;
  }
  const updateSW = mod.registerSW({
    onNeedRefresh: () => {
      useSwUpdateStore.getState().setNeedsRefresh(true, async () => {
        await updateSW(true);
      });
    },
  });
}
