/**
 * Mobile bottom navigation (T020, FR-001, T117 partial).
 *
 * Five documented entries: Library / Wanted / Activity /
 * Settings / Search. Visible on 360 px viewports; hidden on
 * ≥ 768 px (the desktop UX uses the sidebar instead, lands
 * with the Settings sub-pages slice). Each button is a 44 ×
 * 44 px hit target per FR-002.
 *
 * The Search entry opens the global ⌘+K command palette
 * (which lands with the SEARCH phase). Until then it routes
 * to /library — closest existing page that lets the operator
 * find a game.
 *
 * Strings are i18n-resolved (slice 55).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

interface NavEntry {
  to: string;
  /** Key under the `nav.*` namespace. */
  i18nKey: "library" | "wanted" | "activity" | "settings" | "search";
  emoji: string;
}

const ENTRIES: readonly NavEntry[] = [
  { to: "/library", i18nKey: "library", emoji: "📦" },
  { to: "/wanted", i18nKey: "wanted", emoji: "⭐" },
  { to: "/activity", i18nKey: "activity", emoji: "📡" },
  { to: "/settings", i18nKey: "settings", emoji: "⚙️" },
  { to: "/library", i18nKey: "search", emoji: "🔍" },
];

function entryClass(isActive: boolean): string {
  return [
    "flex h-full min-w-[44px] flex-1 flex-col items-center justify-center",
    "gap-0.5 py-1.5 text-[0.65rem] font-medium",
    "transition-colors",
    isActive
      ? "text-brand"
      : "text-zinc-500 hover:text-zinc-200",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
    "focus-visible:rounded",
  ].join(" ");
}

export function BottomNav(): ReactElement {
  const { t } = useTranslation();
  return (
    <nav
      aria-label={t("nav.primary")}
      className={[
        "fixed inset-x-0 bottom-0 z-40 md:hidden",
        "h-14 border-t border-zinc-800 bg-zinc-950/95",
        "backdrop-blur supports-[backdrop-filter]:bg-zinc-950/75",
        "pb-[env(safe-area-inset-bottom)]",
        "flex items-stretch",
      ].join(" ")}
    >
      {ENTRIES.map((entry, index) => (
        <NavLink
          key={`${entry.to}-${index}`}
          to={entry.to}
          end={entry.to === "/library"}
          className={({ isActive }) => entryClass(isActive)}
        >
          <span aria-hidden="true" className="text-base leading-none">
            {entry.emoji}
          </span>
          <span>{t(`nav.${entry.i18nKey}`)}</span>
        </NavLink>
      ))}
    </nav>
  );
}
