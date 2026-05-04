/**
 * SwUpdateToast (CL002).
 *
 * Surfaces the "New version available — Reload" call-to-action
 * when a new service worker is waiting. Wired to the
 * ``useSwUpdateStore`` Zustand store; ``main.tsx`` populates the
 * store via ``registerServiceWorker``.
 *
 * Spec 014 FR-007a: ``skipWaiting`` + ``clients.claim`` +
 * ``window.location.reload()`` only fire on the user's click; a
 * dismiss leaves the prior SW running and the prompt comes back
 * next time the new SW reports.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  applyUpdate,
  dismissUpdate,
  useSwUpdateStore,
} from "@/lib/sw-update";

export function SwUpdateToast(): ReactElement | null {
  const needsRefresh = useSwUpdateStore((s) => s.needsRefresh);
  const { t } = useTranslation("common");

  if (!needsRefresh) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-3 bottom-3 z-50 mx-auto flex max-w-md flex-col gap-2 rounded-lg border border-emerald-700/40 bg-zinc-900/95 p-3 text-sm text-zinc-100 shadow-lg backdrop-blur sm:inset-x-auto sm:right-4 sm:left-auto"
    >
      <div className="font-medium">{t("swUpdate.title")}</div>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={dismissUpdate}
          className="rounded-md px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-100"
        >
          {t("swUpdate.dismiss")}
        </button>
        <button
          type="button"
          onClick={() => {
            void applyUpdate();
          }}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
        >
          {t("swUpdate.reload")}
        </button>
      </div>
    </div>
  );
}
