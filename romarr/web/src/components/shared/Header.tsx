/**
 * App-level header (T019, T117 partial).
 *
 * Today: app title · live-connection indicator · language
 * toggle (EN/FR) · theme toggle (dark / light / auto). Profile
 * menu and ⌘+K command-palette hint land with the SEARCH /
 * P-AUTH phases.
 *
 * The header sticks to the top of the viewport so the bottom
 * nav and content scroll independently — matches the documented
 * 360 px-friendly mobile layout.
 *
 * Strings are resolved through i18next (slice 55, FR-011) —
 * the chrome is the first migration target; pages migrate in
 * their own slices.
 */

import {
  Activity,
  Library as LibraryIcon,
  Monitor,
  Moon,
  Package,
  Search,
  Settings as SettingsIcon,
  Star,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { useQueue } from "@/lib/api/queries/queue";
import { useActiveTasks } from "@/lib/api/queries/system-extras";
import { useSearchStore } from "@/lib/store/search";
import { useThemeStore, type Theme } from "@/lib/store/theme";

import { ConnectionIndicator } from "./ConnectionIndicator";
import { LanguageToggle } from "./LanguageToggle";
import { UpdateCenterBadge } from "./UpdateCenterBadge";

/** Activity badge data shared with the mobile BottomNav.
 *
 * ``count`` aggregates queue rows in any state other than completed
 * (the queue endpoint already prunes completed entries on import)
 * AND scheduler jobs in flight (scan / metadata refresh). ``tone``
 * goes ``warn`` (red) as soon as any queue row is in ``failed`` —
 * the operator needs to look at those.
 *
 * Returns ``count=0`` while either query is loading so the badge
 * doesn't flash on initial mount. */
function useActivityBadge(): { count: number; tone: "info" | "warn" } {
  const queue = useQueue({
    pageSize: 1,
    sortKey: "last_updated_at",
    sortDirection: "desc",
  });
  const failed = useQueue({
    pageSize: 1,
    sortKey: "last_updated_at",
    sortDirection: "desc",
    state: "failed",
  });
  const activeTasks = useActiveTasks();
  const runningTaskCount = (activeTasks.data ?? []).filter(
    (j) => j.current_run_id != null,
  ).length;
  const count = (queue.data?.totalRecords ?? 0) + runningTaskCount;
  const tone: "info" | "warn" =
    (failed.data?.totalRecords ?? 0) > 0 ? "warn" : "info";
  return { count, tone };
}

// Primary desktop navigation. On mobile the BottomNav covers
// these; on md+ the BottomNav is hidden, so the Header carries
// the only way to move between top-level pages.
const DESKTOP_NAV: ReadonlyArray<{
  to: string;
  i18nKey: "library" | "wanted" | "activity" | "romPacks" | "settings";
  Icon: LucideIcon;
  end?: boolean;
}> = [
  // Dashboard intentionally omitted — the page itself is still
  // reachable by typing /dashboard but it's not surfaced in the
  // primary nav (the operator's workflow lives in Library /
  // Wanted / Activity). The route also redirects ``/`` to
  // ``/library`` (see App.tsx) so a bare logo click lands on the
  // useful page.
  { to: "/library", i18nKey: "library", Icon: LibraryIcon },
  { to: "/wanted", i18nKey: "wanted", Icon: Star },
  { to: "/activity", i18nKey: "activity", Icon: Activity },
  { to: "/rom-packs", i18nKey: "romPacks", Icon: Package },
  { to: "/settings", i18nKey: "settings", Icon: SettingsIcon },
];

function navLinkClass(isActive: boolean): string {
  return [
    "inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm",
    "transition-colors",
    isActive
      ? "bg-zinc-800 text-zinc-100"
      : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
  ].join(" ");
}

const THEME_ICON: Record<Theme, LucideIcon> = {
  dark: Moon,
  light: Sun,
  auto: Monitor,
};

// Cycle dark → auto → dark. ``light`` is omitted because most
// components don't yet ship light-theme variants — picking it
// today would leave the app unreadable. Re-enable once the
// component palette gets dark:/light: variants throughout.
const NEXT_THEME: Record<Theme, Theme> = {
  dark: "auto",
  auto: "dark",
  light: "dark",
};

export function Header(): ReactElement {
  const { t } = useTranslation(["common", "search"]);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const openSearch = useSearchStore((s) => s.openModal);
  const activityBadge = useActivityBadge();
  const themeTitle = t("common:theme.title", {
    mode: t(`common:theme.modes.${theme}`),
  });
  const searchTitle = t("search:open");

  return (
    <header
      className={[
        "sticky top-0 z-40",
        "flex items-center justify-between",
        "border-b border-zinc-800 bg-zinc-950/95",
        "backdrop-blur supports-[backdrop-filter]:bg-zinc-950/75",
        "px-4 py-3 sm:px-6",
      ].join(" ")}
    >
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-2.5 rounded-sm bg-brand"
          />
          <span className="font-mono text-sm font-semibold tracking-tight text-zinc-100">
            {t("app.title")}
          </span>
          <UpdateCenterBadge />
        </div>

        {/* Desktop primary nav — hidden on mobile where the
            BottomNav handles top-level routing. */}
        <nav
          aria-label={t("common:nav.primary")}
          className="hidden items-center gap-0.5 md:flex"
        >
          {DESKTOP_NAV.map((entry) => {
            const isActivity = entry.i18nKey === "activity";
            const badgeCount = isActivity ? activityBadge.count : 0;
            return (
              <NavLink
                key={entry.to}
                to={entry.to}
                end={entry.end ?? false}
                className={({ isActive }) =>
                  `relative ${navLinkClass(isActive)}`
                }
              >
                <entry.Icon size={15} strokeWidth={2} aria-hidden="true" />
                <span>{t(`common:nav.${entry.i18nKey}`)}</span>
                {/* Activity badge: same trigger as the BottomNav
                    so the desktop chrome reflects "something is
                    happening or stuck" the moment a queue row or
                    a scheduler job kicks off. Goes red on any
                    failed queue entry. */}
                {badgeCount > 0 && (
                  <span
                    aria-hidden="true"
                    className={[
                      "ml-1 inline-flex h-4 min-w-[1rem]",
                      "items-center justify-center rounded-full px-1",
                      "text-[0.55rem] font-bold leading-none",
                      "ring-1 ring-inset",
                      activityBadge.tone === "warn"
                        ? "bg-red-500/90 text-zinc-50 ring-red-400/40"
                        : "bg-brand text-zinc-950 ring-brand/40",
                    ].join(" ")}
                  >
                    {badgeCount > 99 ? "99+" : badgeCount}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={openSearch}
          aria-label={searchTitle}
          title={searchTitle}
          className={[
            "hidden md:inline-flex h-9 items-center gap-1.5",
            "rounded-md border border-zinc-800 bg-zinc-900/60 px-2",
            "text-xs text-zinc-400",
            "hover:bg-zinc-900 hover:text-zinc-200",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
        >
          <Search size={14} aria-hidden="true" />
          <span className="font-mono text-[0.6rem] uppercase tracking-wider text-zinc-500">
            ⌘K
          </span>
        </button>
        <ConnectionIndicator />
        <LanguageToggle />
        <button
          type="button"
          onClick={() => setTheme(NEXT_THEME[theme])}
          className={[
            "inline-flex h-9 w-9 items-center justify-center rounded-md",
            "border border-zinc-800 bg-zinc-900/60 text-zinc-200",
            "hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
          title={themeTitle}
          aria-label={themeTitle}
        >
          {(() => {
            const Icon = THEME_ICON[theme];
            return <Icon size={16} strokeWidth={2} aria-hidden="true" />;
          })()}
        </button>
      </div>
    </header>
  );
}
