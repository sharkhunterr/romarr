/**
 * Settings > Platforms page test (spec 014 P-SET).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { PlatformsPage } from "./index";
import * as platformPacksQuery from "@/lib/api/queries/platform-packs";

const I18N_BUNDLE = {
  settings: {
    platforms: {
      title: "Platforms",
      subtitle: "Per-console catalogue + Platform Packs.",
      empty: { title: "No platform packs", body: "Apply a built-in pack." },
      emptyBanner: {
        title: "No platforms defined",
        body: "Community-first bootstrap runs in the background.",
        hint: "Wait a few seconds and refresh.",
      },
      uploadHint: "Upload a YAML pack via /api/v3/platform/pack.",
    },
  },
};

describe("PlatformsPage", () => {
  it("renders the empty-state banner when usePlatformPacks returns []", () => {
    vi.spyOn(platformPacksQuery, "usePlatformPacks").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof platformPacksQuery.usePlatformPacks>);

    renderWithProviders(<PlatformsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Platforms")).toBeInTheDocument();
    expect(screen.getByText("No platforms defined")).toBeInTheDocument();
  });

  it("surfaces the API error in the EmptyState when the query fails", () => {
    vi.spyOn(platformPacksQuery, "usePlatformPacks").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "platform pack table missing" },
    } as unknown as ReturnType<typeof platformPacksQuery.usePlatformPacks>);

    renderWithProviders(<PlatformsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("platform pack table missing")).toBeInTheDocument();
  });
});
