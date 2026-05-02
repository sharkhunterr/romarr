/**
 * Offline fallback page (T058).
 *
 * Rendered by the service worker as the navigation fallback
 * when the network is down AND the requested page isn't in the
 * cache (the SW configures /index.html as the navigateFallback,
 * so the SPA shell is normally available; this page covers the
 * pathological case where even the shell is missing).
 *
 * The page is intentionally tiny — it has to render with zero
 * runtime data. "Try again" simply reloads the route.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

export function OfflinePage(): ReactElement {
  const { t } = useTranslation("common");
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-50">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6 text-center">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("offline.title")}
        </h1>
        <p className="text-sm text-zinc-400">{t("offline.body")}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className={[
            "inline-flex h-10 items-center justify-center rounded-md px-4",
            "bg-brand text-sm font-medium text-zinc-900",
            "hover:bg-brand-300",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
        >
          {t("offline.retry")}
        </button>
      </div>
    </main>
  );
}
