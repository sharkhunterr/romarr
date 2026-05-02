/**
 * Settings layout (T105, T117 partial).
 *
 * Desktop (md+): 16-rem sidebar + outlet grid.
 * Mobile: nav stacks above the outlet — both as a single
 * scrollable column.
 *
 * This component sits between the AppLayout and each Settings
 * sub-page. The sub-pages (Tags + UI shipped; the rest
 * placeholders) render through <Outlet />.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router-dom";

import { SettingsNav } from "./SettingsNav";

export function SettingsLayout(): ReactElement {
  const { t } = useTranslation("settings");
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
      </header>

      <div className="grid gap-4 md:grid-cols-[16rem_minmax(0,1fr)] md:gap-6">
        <SettingsNav />
        <main className="min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
