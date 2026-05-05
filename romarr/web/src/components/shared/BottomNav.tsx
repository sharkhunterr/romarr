/**
 * Mobile bottom navigation (T020, FR-001, T117 partial).
 *
 * Five documented entries: Library / Wanted / Activity /
 * Settings / Search. Visible on 360 px viewports; hidden on
 * ≥ 768 px (the desktop UX uses the sidebar instead). Each
 * button is a 44 × 44 px hit target per FR-002.
 *
 * The Search entry opens the global ⌘+K command palette
 * (slice 71); the rest are NavLink routes.
 *
 * Strings are i18n-resolved (slice 55).
 */

import {
  Activity,
  Library as LibraryIcon,
  Search,
  Settings,
  Star,
  type LucideIcon,
} from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { useSearchStore } from "@/lib/store/search";

type RouteEntry = {
  kind: "route";
  to: string;
  i18nKey: "library" | "wanted" | "activity" | "settings";
  Icon: LucideIcon;
};

type ActionEntry = {
  kind: "action";
  i18nKey: "search";
  Icon: LucideIcon;
};

type NavEntry = RouteEntry | ActionEntry;

const ENTRIES: readonly NavEntry[] = [
  { kind: "route", to: "/library", i18nKey: "library", Icon: LibraryIcon },
  { kind: "route", to: "/wanted", i18nKey: "wanted", Icon: Star },
  { kind: "route", to: "/activity", i18nKey: "activity", Icon: Activity },
  { kind: "route", to: "/settings", i18nKey: "settings", Icon: Settings },
  { kind: "action", i18nKey: "search", Icon: Search },
];

function entryClass(isActive: boolean): string {
  return [
    "flex h-full min-w-[44px] flex-1 flex-col items-center justify-center",
    "gap-0.5 py-1.5",
    "transition-colors",
    isActive
      ? "text-brand"
      : "text-zinc-400 hover:text-zinc-100",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
    "focus-visible:rounded",
  ].join(" ");
}

function NavEntryNode(props: { entry: NavEntry; index: number }): ReactElement {
  const { t } = useTranslation();
  const openSearch = useSearchStore((s) => s.openModal);
  const { entry } = props;
  const label = t(`nav.${entry.i18nKey}`);

  if (entry.kind === "action") {
    return (
      <button
        key={`search-${props.index}`}
        type="button"
        onClick={openSearch}
        aria-label={label}
        title={label}
        className={entryClass(false)}
      >
        <entry.Icon size={24} strokeWidth={2} aria-hidden="true" />
      </button>
    );
  }

  return (
    <NavLink
      key={`${entry.to}-${props.index}`}
      to={entry.to}
      end={entry.to === "/library"}
      aria-label={label}
      title={label}
      className={({ isActive }) => entryClass(isActive)}
    >
      {({ isActive }) => (
        <entry.Icon
          size={24}
          strokeWidth={isActive ? 2.4 : 2}
          aria-hidden="true"
        />
      )}
    </NavLink>
  );
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
        <NavEntryNode key={index} entry={entry} index={index} />
      ))}
    </nav>
  );
}
