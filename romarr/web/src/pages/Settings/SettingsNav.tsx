/**
 * Settings navigation (T105, T117/T119 partial).
 *
 * Desktop (md+): a sticky 16-rem sidebar column of NavLinks.
 * Mobile (< md): a single ``<select>`` dropdown — stacking the
 * full entry list above every sub-page wasted the whole first
 * screen on a phone.
 *
 * Icons resolve to lucide-react components; labels resolve
 * through `settings:nav.<slug>`.
 */

import {
  Archive,
  Bell,
  CloudDownload,
  Database,
  Download,
  FileQuestion,
  FileText,
  FolderTree,
  Gamepad2,
  HelpCircle,
  Package,
  Palette,
  Search,
  Settings as SettingsIcon,
  SlidersHorizontal,
  Tag,
  type LucideIcon,
} from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

export interface SettingsNavEntry {
  to: string;
  /** Path slug used as the i18n key under `settings:nav.<slug>`. */
  slug: string;
  Icon: LucideIcon;
  shipped?: boolean;
}

export const SETTINGS_NAV_ENTRIES: readonly SettingsNavEntry[] = [
  { to: "/settings/general", slug: "general", Icon: SettingsIcon, shipped: true },
  { to: "/settings/profiles", slug: "profiles", Icon: SlidersHorizontal, shipped: true },
  { to: "/settings/media-management", slug: "media-management", Icon: FolderTree, shipped: true },
  { to: "/settings/indexers", slug: "indexers", Icon: Search, shipped: true },
  { to: "/settings/download-clients", slug: "download-clients", Icon: Download, shipped: true },
  { to: "/settings/dat-sources", slug: "dat-sources", Icon: Database, shipped: true },
  { to: "/settings/rom-packs", slug: "rom-packs", Icon: Package, shipped: true },
  { to: "/settings/metadata-sources", slug: "metadata-sources", Icon: FileQuestion, shipped: true },
  { to: "/settings/platforms", slug: "platforms", Icon: Gamepad2, shipped: true },
  { to: "/settings/connect", slug: "connect", Icon: Bell, shipped: true },
  { to: "/settings/tags", slug: "tags", Icon: Tag, shipped: true },
  { to: "/settings/unidentified", slug: "unidentified", Icon: HelpCircle, shipped: true },
  { to: "/settings/ui", slug: "ui", Icon: Palette, shipped: true },
  { to: "/settings/logs", slug: "logs", Icon: FileText, shipped: true },
  { to: "/settings/backup", slug: "backup", Icon: Archive, shipped: true },
  { to: "/settings/updates", slug: "updates", Icon: CloudDownload, shipped: true },
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
  const navigate = useNavigate();
  const location = useLocation();

  // The active entry — longest matching ``to`` prefix so e.g.
  // ``/settings/profiles/edit`` still selects the Profiles row.
  const current =
    SETTINGS_NAV_ENTRIES.filter((e) =>
      location.pathname.startsWith(e.to),
    ).sort((a, b) => b.to.length - a.to.length)[0]?.to ??
    "/settings/general";

  return (
    <>
      {/* Mobile — single dropdown instead of a tall stacked list. */}
      <label className="block md:hidden">
        <span className="sr-only">{t("nav.ariaLabel")}</span>
        <select
          value={current}
          onChange={(e) => navigate(e.target.value)}
          aria-label={t("nav.ariaLabel")}
          className={[
            "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
            "ring-1 ring-inset ring-zinc-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {SETTINGS_NAV_ENTRIES.map((entry) => (
            <option key={entry.to} value={entry.to}>
              {t(`nav.${entry.slug}`)}
              {entry.shipped !== true ? ` — ${t("nav.comingSoon")}` : ""}
            </option>
          ))}
        </select>
      </label>

      {/* Desktop — sticky sidebar list. */}
      <nav
        aria-label={t("nav.ariaLabel")}
        className="hidden flex-col gap-1 md:flex md:sticky md:top-20 md:self-start"
      >
        {SETTINGS_NAV_ENTRIES.map((entry) => (
          <NavLink
            key={entry.to}
            to={entry.to}
            end
            className={({ isActive }) => entryClass(isActive)}
          >
            <entry.Icon size={16} aria-hidden="true" className="shrink-0" />
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
    </>
  );
}
