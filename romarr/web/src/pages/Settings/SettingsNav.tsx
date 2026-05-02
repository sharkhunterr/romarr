/**
 * Settings sidebar / mobile list nav (T105).
 *
 * Twelve entries, in workflow order. Desktop: 16-rem sidebar
 * column (md+). Mobile: vertical list above the outlet (the
 * grid collapses to a single column).
 *
 * Tags is the only sub-page implemented today (slice 51); the
 * rest land in their own slices and currently render the
 * placeholder. The "shipped" badge marks pages that have a
 * real implementation behind them.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { NavLink } from "react-router-dom";

interface NavEntry {
  to: string;
  label: string;
  emoji: string;
  shipped?: boolean;
}

const ENTRIES: readonly NavEntry[] = [
  { to: "/settings/profiles", label: "Profiles", emoji: "🎚️" },
  { to: "/settings/media-management", label: "Media Management", emoji: "📁" },
  { to: "/settings/quality-definitions", label: "Quality Definitions", emoji: "📐" },
  { to: "/settings/indexers", label: "Indexers", emoji: "🔍" },
  { to: "/settings/download-clients", label: "Download Clients", emoji: "⬇️" },
  { to: "/settings/dat-sources", label: "DAT Sources", emoji: "📋" },
  { to: "/settings/metadata-sources", label: "Metadata Sources", emoji: "🗂️" },
  { to: "/settings/platforms", label: "Platforms", emoji: "🎮" },
  { to: "/settings/connect", label: "Connect", emoji: "🔔" },
  { to: "/settings/tags", label: "Tags", emoji: "🏷️", shipped: true },
  { to: "/settings/ui", label: "UI", emoji: "🎨" },
  { to: "/settings/general", label: "General", emoji: "⚙️" },
];

function entryClass(isActive: boolean): string {
  return [
    "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
    "transition-colors",
    isActive
      ? "bg-zinc-800 text-zinc-100"
      : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
    "focus-visible:outline-none focus-visible:ring-2",
    "focus-visible:ring-brand",
  ].join(" ");
}

export function SettingsNav(): ReactElement {
  return (
    <nav
      aria-label="Settings sub-pages"
      className="flex flex-col gap-1 md:sticky md:top-20 md:self-start"
    >
      {ENTRIES.map((entry) => (
        <NavLink
          key={entry.to}
          to={entry.to}
          end
          className={({ isActive }) => entryClass(isActive)}
        >
          <span aria-hidden="true" className="text-base leading-none">
            {entry.emoji}
          </span>
          <span className="flex-1">{entry.label}</span>
          {entry.shipped !== true && (
            <span
              aria-hidden="true"
              className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[0.55rem] font-medium uppercase tracking-wider text-zinc-500"
              title="Coming soon"
            >
              soon
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export const SETTINGS_NAV_ENTRIES = ENTRIES;
