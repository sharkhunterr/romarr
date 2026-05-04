/**
 * Settings > Metadata sources page test (spec 014 P-SET).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { MetadataSourcesPage } from "./index";
import * as metadataSourcesQuery from "@/lib/api/queries/metadata-sources";

const I18N_BUNDLE = {
  settings: {
    metadataSources: {
      title: "Metadata sources",
      subtitle: "Per-field provider priority.",
      empty: {
        title: "No metadata providers",
        body: "Configure IGDB or ScreenScraper to get started.",
      },
      fieldPriorityHint: "Per-field priority editor lands in a follow-up slice.",
    },
  },
};

describe("MetadataSourcesPage", () => {
  it("renders the empty-state when useMetadataProviders returns []", () => {
    vi.spyOn(metadataSourcesQuery, "useMetadataProviders").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof metadataSourcesQuery.useMetadataProviders>);

    renderWithProviders(<MetadataSourcesPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("Metadata sources")).toBeInTheDocument();
    expect(screen.getByText("No metadata providers")).toBeInTheDocument();
  });

  it("surfaces the API error in the EmptyState when the query fails", () => {
    vi.spyOn(metadataSourcesQuery, "useMetadataProviders").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "metadata provider table missing" },
    } as unknown as ReturnType<typeof metadataSourcesQuery.useMetadataProviders>);

    renderWithProviders(<MetadataSourcesPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(
      screen.getByText("metadata provider table missing"),
    ).toBeInTheDocument();
  });
});
