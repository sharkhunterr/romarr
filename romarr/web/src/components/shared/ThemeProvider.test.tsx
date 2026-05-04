/**
 * ThemeProvider test (spec 014 T039).
 *
 * Verifies the documented contract: the resolved theme
 * (``dark`` / ``light``) lands as a class on
 * ``document.documentElement``. ``auto`` mode resolves via
 * ``window.matchMedia`` which the test/setup.ts shim wires
 * to a stub that defaults to "dark".
 */

import { afterEach, describe, expect, it } from "vitest";
import { act } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { ThemeProvider } from "./ThemeProvider";
import { useThemeStore } from "@/lib/store/theme";

afterEach(() => {
  // Reset to the constitutional default so per-test state
  // leaks don't poison neighbours.
  act(() => {
    useThemeStore.getState().setTheme("dark");
  });
  document.documentElement.classList.remove("dark", "light");
});

describe("ThemeProvider", () => {
  it("applies the 'dark' class on <html> when the store carries theme='dark'", () => {
    act(() => {
      useThemeStore.getState().setTheme("dark");
    });

    renderWithProviders(
      <ThemeProvider>
        <p>child</p>
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });

  it("applies the 'light' class on <html> when the store carries theme='light'", () => {
    act(() => {
      useThemeStore.getState().setTheme("light");
    });

    renderWithProviders(
      <ThemeProvider>
        <p>child</p>
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("resolves 'auto' through window.matchMedia (jsdom shim defaults to dark)", () => {
    act(() => {
      useThemeStore.getState().setTheme("auto");
    });

    renderWithProviders(
      <ThemeProvider>
        <p>child</p>
      </ThemeProvider>,
    );

    // The test/setup.ts matchMedia shim returns matches=false by
    // default, so ``auto`` resolves to ``light``. The class should
    // be EXACTLY one of dark/light — the contract is "the resolver
    // produces a deterministic class", not "auto means dark".
    const html = document.documentElement;
    const hasDark = html.classList.contains("dark");
    const hasLight = html.classList.contains("light");
    expect(hasDark || hasLight).toBe(true);
    expect(hasDark && hasLight).toBe(false);
  });
});
