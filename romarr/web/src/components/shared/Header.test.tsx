/**
 * Header test (spec 014 P-DASH chrome).
 *
 * The header composes the app title, the global ⌘K
 * shortcut button (md+ only), the live connection
 * indicator, the language toggle (EN/FR pills), and the
 * theme cycle button. We verify the always-rendered
 * elements + the theme cycle wiring (dark → light → auto →
 * dark).
 */

import { afterEach, describe, expect, it } from "vitest";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { Header } from "./Header";
import { useThemeStore } from "@/lib/store/theme";

const I18N_BUNDLE = {
  common: {
    app: { title: "Romarr" },
    theme: {
      title: "Theme: {{mode}}",
      modes: { dark: "Dark", light: "Light", auto: "Auto" },
    },
  },
  search: { open: "Open search (⌘K)" },
  translation: {
    language: { label: "Language" },
    connection: { idle: "Idle", connected: "Live" },
  },
};

afterEach(() => {
  act(() => {
    useThemeStore.getState().setTheme("dark");
  });
});

describe("Header", () => {
  it("renders the app title + the ⌘K button + the theme cycle button", () => {
    renderWithProviders(<Header />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Romarr")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Open search/ }),
    ).toBeInTheDocument();
    // Theme button — the active glyph is rendered as the
    // button's content; the title carries the mode name.
    expect(
      screen.getByRole("button", { name: "Theme: Dark" }),
    ).toBeInTheDocument();
  });

  it("cycles theme dark ↔ auto on each click (light deferred)", async () => {
    act(() => {
      useThemeStore.getState().setTheme("dark");
    });

    const user = userEvent.setup();
    renderWithProviders(<Header />, { i18nResources: I18N_BUNDLE });

    const themeButton = screen.getByRole("button", { name: "Theme: Dark" });
    await user.click(themeButton);
    expect(useThemeStore.getState().theme).toBe("auto");

    await user.click(screen.getByRole("button", { name: "Theme: Auto" }));
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("renders the language picker dropdown", () => {
    renderWithProviders(<Header />, { i18nResources: I18N_BUNDLE });

    const combobox = screen.getByRole("combobox", { name: /language/i });
    expect(combobox).toBeInTheDocument();
  });
});
