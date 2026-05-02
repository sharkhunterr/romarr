/**
 * Settings sidebar / mobile list nav (T105, T117/T119 partial).
 *
 * Twelve entries, in workflow order. Desktop: 16-rem sidebar
 * column (md+). Mobile: vertical list above the outlet (the
 * grid collapses to a single column).
 *
 * Tags + UI are the implemented sub-pages today (slices 51 +
 * 56); the rest land in their own slices and currently render
 * the placeholder. The "shipped" badge marks pages that have a
 * real implementation behind them.
 *
 * Labels resolve through `settings:nav.<slug>` (slice 56).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

export interface SettingsNavEntry {
  to: string;
  /** Path slug used as the i18n key under `settings:nav.<slug>`. */
  slug: string;
  emoji: string;
  shipped?: boolean;
}

export const SETTINGS_NAV_ENTRIES: readonly SettingsNavEntry[] = [
  { to: "/settings/profiles", slug: "profiles", emoji: "🎚️" },
  { to: "/settings/media-management", slug: "media-management", emoji: "📁" },
  { to: "/settings/quality-definitions", slug: "quality-definitions", emoji: "📐" },
  { to: "/settings/indexers", slug: "indexers", emoji: "🔍", shipped: true },
  { to: "/settings/download-clients", slug: "download-clients", emoji: "⬇️", shipped: true },
  { to: "/settings/dat-sources", slug: "dat-sources", emoji: "📋" },
  { to: "/settings/metadata-sources", slug: "metadata-sources", emoji: "🗂️" },
  { to: "/settings/platforms", slug: "platforms", emoji: "🎮" },
  { to: "/settings/connect", slug: "connect", emoji: "🔔" },
  { to: "/settings/tags", slug: "tags", emoji: "🏷️", shipped: true },
  { to: "/settings/ui", slug: "ui", emoji: "🎨", shipped: true },
  { to: "/settings/general", slug: "general", emoji: "⚙️" },
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
  const { t } = useTranslation("settings");
  return (
    <nav
      aria-label={t("nav.ariaLabel")}
      className="flex flex-col gap-1 md:sticky md:top-20 md:self-start"
    >
      {SETTINGS_NAV_ENTRIES.map((entry) => (
        <NavLink
          key={entry.to}
          to={entry.to}
          end
          className={({ isActive }) => entryClass(isActive)}
        >
          <span aria-hidden="true" className="text-base leading-none">
            {entry.emoji}
          </span>
          <span className="flex-1">{t(`nav.${entry.slug}`)}</span>
          {entry.shipped !== true && (
            <span
              aria-hidden="true"
              className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[0.55rem] font-medium uppercase tracking-wider text-zinc-500"
              title={t("nav.comingSoon")}
            >
              {t("nav.comingSoon")}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
