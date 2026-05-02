/**
 * Mobile bottom navigation (T020, FR-001).
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
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { NavLink } from "react-router-dom";

interface NavEntry {
  to: string;
  label: string;
  emoji: string;
}

const ENTRIES: readonly NavEntry[] = [
  { to: "/library", label: "Library", emoji: "📦" },
  { to: "/wanted", label: "Wanted", emoji: "⭐" },
  { to: "/activity", label: "Activity", emoji: "📡" },
  { to: "/settings", label: "Settings", emoji: "⚙️" },
  { to: "/library", label: "Search", emoji: "🔍" },
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
  return (
    <nav
      aria-label="Primary navigation"
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
          <span>{entry.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
