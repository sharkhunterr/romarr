/**
 * ThemeProvider (T043, FR-013).
 *
 * Reads the persisted theme choice from the zustand store and
 * applies the resolved class (``dark`` or ``light``) on
 * ``<html>``. ``auto`` mode subscribes to
 * ``prefers-color-scheme`` so the OS preference flips the
 * palette without a refresh.
 *
 * No-flash story: an inline script in index.html applies the
 * persisted class BEFORE React hydrates, so the very first
 * paint is already correct. This component takes over once
 * React is mounted (re-applying the same class is a no-op the
 * browser doesn't repaint for).
 */

import { useEffect, type ReactElement, type ReactNode } from "react";

import { resolveTheme, useThemeStore } from "@/lib/store/theme";

export interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider(
  props: ThemeProviderProps,
): ReactElement {
  const theme = useThemeStore((s) => s.theme);

  // Apply the resolved theme to the <html> class on every change.
  useEffect(() => {
    const apply = (): void => {
      const resolved = resolveTheme(theme);
      const html = document.documentElement;
      html.classList.toggle("dark", resolved === "dark");
      html.classList.toggle("light", resolved === "light");
    };
    apply();
    // ``auto`` mode: react to OS preference changes too.
    if (theme === "auto" && typeof window !== "undefined") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
    return undefined;
  }, [theme]);

  return <>{props.children}</>;
}
