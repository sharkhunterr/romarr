/**
 * Settings > Platforms page test.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { PlatformsPage } from "./index";
import * as platformsQuery from "@/lib/api/queries/platforms";

const I18N_BUNDLE = {
  settings: {
    platforms: {
      title: "Platforms",
      subtitle: "Per-console catalogue + Platform Packs.",
      emptyBanner: {
        title: "No platforms defined",
        body: "Community-first bootstrap runs in the background.",
        hint: "Wait a few seconds and refresh.",
      },
      catalogue: {
        heading: "Catalogue",
        subhead: "{{count}} platforms",
        filterPlaceholder: "Filter…",
        noMatches: "No matches",
        loadError: "Load error",
      },
    },
  },
};

describe("PlatformsPage", () => {
  it("renders the empty-state banner when usePlatforms returns []", () => {
    vi.spyOn(platformsQuery, "usePlatforms").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof platformsQuery.usePlatforms>);

    renderWithProviders(<PlatformsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Platforms")).toBeInTheDocument();
    expect(screen.getByText("No platforms defined")).toBeInTheDocument();
  });

  it("surfaces the API error when the platforms query fails", () => {
    vi.spyOn(platformsQuery, "usePlatforms").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "platform table missing" },
    } as unknown as ReturnType<typeof platformsQuery.usePlatforms>);

    renderWithProviders(<PlatformsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("platform table missing")).toBeInTheDocument();
  });
});
