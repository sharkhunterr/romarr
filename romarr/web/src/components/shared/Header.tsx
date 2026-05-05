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

import { Search } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useSearchStore } from "@/lib/store/search";
import { useThemeStore, type Theme } from "@/lib/store/theme";

import { ConnectionIndicator } from "./ConnectionIndicator";
import { LanguageToggle } from "./LanguageToggle";

const THEME_GLYPH: Record<Theme, string> = {
  dark: "🌙",
  light: "☀️",
  auto: "💻",
};

const NEXT_THEME: Record<Theme, Theme> = {
  dark: "light",
  light: "auto",
  auto: "dark",
};

export function Header(): ReactElement {
  const { t } = useTranslation(["common", "search"]);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const openSearch = useSearchStore((s) => s.openModal);
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
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-2.5 w-2.5 rounded-sm bg-brand"
        />
        <span className="font-mono text-sm font-semibold tracking-tight text-zinc-100">
          {t("app.title")}
        </span>
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
            "text-base hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
          title={themeTitle}
          aria-label={themeTitle}
        >
          {THEME_GLYPH[theme]}
        </button>
      </div>
    </header>
  );
}
