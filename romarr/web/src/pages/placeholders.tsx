/**
 * Placeholder pages (ROUTING phase).
 *
 * Each page is a stub that proves the route resolves and shows
 * the operator the title + a "coming soon" indicator. Real
 * implementations land in the per-page phases (P-LIB / P-ADD /
 * P-GAME).
 *
 * Strings resolve through `common:placeholder.*` (slice 70).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

interface PageShellProps {
  titleKey: string;
  subtitleKey: string;
}

function PageShell(props: PageShellProps): ReactElement {
  const { t } = useTranslation("common");
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto max-w-md px-4 py-12">
        <h1 className="font-mono text-2xl font-semibold text-brand">
          {t(props.titleKey)}
        </h1>
        <p className="mt-3 text-sm text-zinc-400">{t(props.subtitleKey)}</p>
        <p className="mt-8 font-mono text-xs uppercase tracking-widest text-zinc-600">
          {t("placeholder.comingSoon")}
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
      titleKey="placeholder.library.title"
      subtitleKey="placeholder.library.subtitle"
    />
  );
}

export function AddNewPage(): ReactElement {
  return (
    <PageShell
      titleKey="placeholder.addNew.title"
      subtitleKey="placeholder.addNew.subtitle"
    />
  );
}

export function GameDetailPage(): ReactElement {
  return (
    <PageShell
      titleKey="placeholder.gameDetail.title"
      subtitleKey="placeholder.gameDetail.subtitle"
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

// SetupPage is shipped (slice 59) at @/pages/Setup/index.tsx.

export function NotFoundPage(): ReactElement {
  return (
    <PageShell
      titleKey="placeholder.notFound.title"
      subtitleKey="placeholder.notFound.subtitle"
    />
  );
}
