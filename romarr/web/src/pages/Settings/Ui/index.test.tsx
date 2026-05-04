/**
 * Settings > UI page test (spec 014 P-SET, T119 follow-up).
 *
 * The page wires three operator-facing controls: theme
 * (3 pills) + language (2 pills) + the optional install
 * prompt section. Theme + language come from a Zustand
 * store + i18next; we let those run unmocked because they
 * have deterministic defaults (theme = "dark", language =
 * "en"). The PWA install plumbing is mocked so the
 * conditional Install section can be verified in both
 * "absent" and "present" states.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { SettingsUiPage } from "./index";
import * as installModule from "@/lib/pwa/install";

const I18N_BUNDLE = {
  settings: {
    ui: {
      title: "User interface",
      subtitle: "Theme, language, install.",
      theme: { label: "Theme", help: "Stored in localStorage." },
      language: { label: "Language", help: "Stored in localStorage." },
      install: { label: "Installed", help: "Add Romarr to your home screen." },
    },
  },
  common: {
    theme: { modes: { dark: "Dark", light: "Light", auto: "Auto" } },
    language: { english: "English", french: "Français" },
  },
};

describe("SettingsUiPage", () => {
  it("renders the Theme + Language sections without the install panel when PWA isn't installable", () => {
    vi.spyOn(installModule, "useInstallPrompt").mockReturnValue({
      canInstall: false,
      isInstalled: false,
      promptInstall: vi.fn(),
    } as unknown as ReturnType<typeof installModule.useInstallPrompt>);

    renderWithProviders(<SettingsUiPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("User interface")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Theme" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Language" }),
    ).toBeInTheDocument();
    // Three theme pills.
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Auto" })).toBeInTheDocument();
    // Two language pills.
    expect(
      screen.getByRole("button", { name: "English" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Français" }),
    ).toBeInTheDocument();
    // Install section MUST NOT render when canInstall=false +
    // isInstalled=false.
    expect(
      screen.queryByRole("heading", { name: "Installed" }),
    ).toBeNull();
  });

  it("renders the install panel when the PWA can be installed", () => {
    vi.spyOn(installModule, "useInstallPrompt").mockReturnValue({
      canInstall: true,
      isInstalled: false,
      promptInstall: vi.fn(),
    } as unknown as ReturnType<typeof installModule.useInstallPrompt>);

    renderWithProviders(<SettingsUiPage />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByRole("heading", { name: "Installed" }),
    ).toBeInTheDocument();
  });
});
