/**
 * App-level header (T019).
 *
 * Today's slice: app title + theme toggle (dark / light /
 * auto). Language toggle, profile menu, OfflineIndicator slot,
 * and ⌘+K command-palette hint land with their owning phases
 * (I18N / P-AUTH / WS / SEARCH).
 *
 * The header sticks to the top of the viewport so the bottom
 * nav and content scroll independently — matches the documented
 * 360 px-friendly mobile layout.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { useThemeStore, type Theme } from "@/lib/store/theme";

const THEME_LABEL: Record<Theme, string> = {
  dark: "🌙",
  light: "☀️",
  auto: "💻",
};

const THEME_TITLE: Record<Theme, string> = {
  dark: "Theme: dark",
  light: "Theme: light",
  auto: "Theme: auto",
};

const NEXT_THEME: Record<Theme, Theme> = {
  dark: "light",
  light: "auto",
  auto: "dark",
};

export function Header(): ReactElement {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

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
          Romarr
        </span>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setTheme(NEXT_THEME[theme])}
          className={[
            "inline-flex h-9 w-9 items-center justify-center rounded-md",
            "text-base hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
          title={THEME_TITLE[theme]}
          aria-label={THEME_TITLE[theme]}
        >
          {THEME_LABEL[theme]}
        </button>
      </div>
    </header>
  );
}
