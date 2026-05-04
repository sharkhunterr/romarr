/**
 * Settings > Profiles page test (spec 014 P-SET, T096).
 *
 * The page is a six-tab switcher: Quality / Region / Dump /
 * Language / Naming / Custom Formats. Each tab pulls its own
 * query, so the test focuses on the page-level contract:
 * the six tab buttons render, the Quality tab is active by
 * default. The active tab's body is left intentionally
 * un-asserted because that's covered by per-tab test files.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { ProfilesPage } from "./index";
import * as qualityProfilesQuery from "@/lib/api/queries/quality-profiles";

const I18N_BUNDLE = {
  settings: {
    profiles: {
      title: "Profiles",
      subtitle: "Quality / Region / Dump / Language / Naming / Custom.",
      tabs: {
        quality: "Quality",
        region: "Region",
        dump: "Dump",
        language: "Language",
        naming: "Naming",
        "custom-formats": "Custom Formats",
      },
      empty: { title: "No quality profiles", body: "Defaults will seed." },
    },
  },
};

describe("ProfilesPage", () => {
  it("renders all six tab buttons with Quality active by default", () => {
    vi.spyOn(qualityProfilesQuery, "useQualityProfiles").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<
      typeof qualityProfilesQuery.useQualityProfiles
    >);

    renderWithProviders(<ProfilesPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Profiles")).toBeInTheDocument();
    const qualityTab = screen.getByRole("button", { name: /^Quality$/ });
    expect(qualityTab).toHaveAttribute("aria-pressed", "true");
    // The remaining five tabs render and start un-pressed.
    for (const label of ["Region", "Dump", "Language", "Naming", "Custom Formats"]) {
      const tab = screen.getByRole("button", { name: new RegExp(`^${label}$`) });
      expect(tab).toHaveAttribute("aria-pressed", "false");
    }
  });
});
