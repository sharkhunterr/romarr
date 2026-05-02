/**
 * Theme store (T043, FR-013).
 *
 * Persists the operator's choice (``dark`` / ``light`` / ``auto``)
 * in localStorage under :const:`THEME_STORAGE_KEY` so a refresh
 * doesn't flash the wrong palette. The ``auto`` mode follows
 * the OS via ``prefers-color-scheme``; the resolved class is
 * ``dark`` or ``light`` set on ``<html>``.
 *
 * The no-flash inline script in ``index.html`` reads this same
 * key BEFORE React hydration so the very first paint already has
 * the right ``class="dark"`` toggle.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light" | "auto";

export const THEME_STORAGE_KEY = "romarr.theme";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "dark", // Constitutional default per spec 014.
      setTheme: (theme) => set({ theme }),
    }),
    { name: THEME_STORAGE_KEY },
  ),
);

/**
 * Resolve a chosen theme to the concrete value that should be
 * applied as a class on ``<html>``. ``auto`` reads the OS via
 * ``window.matchMedia``.
 */
export function resolveTheme(theme: Theme): "dark" | "light" {
  if (theme === "auto") {
    if (typeof window === "undefined") {
      return "dark";
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return theme;
}
