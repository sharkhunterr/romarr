/**
 * Settings layout (T105).
 *
 * Desktop (md+): 16-rem sidebar + outlet grid.
 * Mobile: nav stacks above the outlet — both as a single
 * scrollable column.
 *
 * This component sits between the AppLayout and each Settings
 * sub-page. The sub-pages (Tags shipped; the rest placeholders)
 * render through <Outlet />.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { Outlet } from "react-router-dom";

import { SettingsNav } from "./SettingsNav";

export function SettingsLayout(): ReactElement {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          Settings
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Profiles, indexers, download clients, identification sources, and
          notifications.
        </p>
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
