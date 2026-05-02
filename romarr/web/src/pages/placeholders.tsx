/**
 * Placeholder pages (ROUTING phase).
 *
 * Each page is a stub that proves the route resolves and shows
 * the operator the title + a "coming soon" indicator. Real
 * implementations land in the per-page phases (P-DASH /
 * P-LIB / P-ADD / P-GAME / P-WANT / P-ACT / P-CAL / P-SET /
 * P-SYS / P-AUTH / P-SETUP).
 *
 * Login + Setup are the only public pages today (no AuthGuard);
 * the rest sit behind the guard in the route table.
 */

/* eslint-disable react/jsx-no-literals */

import { type ReactElement } from "react";

function PageShell(props: {
  title: string;
  subtitle?: string;
}): ReactElement {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto max-w-md px-4 py-12">
        <h1 className="font-mono text-2xl font-semibold text-brand">
          {props.title}
        </h1>
        {props.subtitle && (
          <p className="mt-3 text-sm text-zinc-400">{props.subtitle}</p>
        )}
        <p className="mt-8 font-mono text-xs uppercase tracking-widest text-zinc-600">
          coming soon · placeholder
        </p>
      </div>
    </main>
  );
}

// DashboardPage is the first real page implementation; lives at
// @/pages/Dashboard/index.tsx (slice 47, P-DASH).

export function LibraryPage(): ReactElement {
  return (
    <PageShell
      title="Library"
      subtitle="Game grid with filtering / bulk select (P-LIB phase)."
    />
  );
}

export function AddNewPage(): ReactElement {
  return (
    <PageShell
      title="Add New"
      subtitle="IGDB/SS metadata search + add (P-ADD phase)."
    />
  );
}

export function GameDetailPage(): ReactElement {
  return (
    <PageShell
      title="Game"
      subtitle="Tabbed detail (Overview / Releases / History / Files / Manual Search / Notes) — P-GAME phase."
    />
  );
}

// WantedPage is the second real page implementation; lives at
// @/pages/Wanted/index.tsx (slice 48, P-WANT).

// ActivityPage is the third real page implementation; lives at
// @/pages/Activity/index.tsx (slice 49, P-ACT).

// CalendarPage is the fifth real page implementation; lives at
// @/pages/Calendar/index.tsx (slice 52, P-CAL). Intentionally
// not surfaced in the bottom nav — kept reachable by direct
// URL only.

// SettingsPage is shipped (slice 53) at @/pages/Settings/
// SettingsLayout + SettingsHome + SettingsPlaceholder. The
// only real sub-page today is Tags (slice 51); the rest render
// the placeholder under the same sidebar shell.

// SystemPage is the fourth real page implementation; lives at
// @/pages/System/index.tsx (slice 50, P-SYS).

// LoginPage is shipped (slice 58) at @/pages/Login/index.tsx.

export function SetupPage(): ReactElement {
  return (
    <PageShell
      title="Welcome to Romarr"
      subtitle="First-boot wizard (P-SETUP phase)."
    />
  );
}

export function NotFoundPage(): ReactElement {
  return (
    <PageShell
      title="404 — Not found"
      subtitle="The route you followed doesn't exist."
    />
  );
}
