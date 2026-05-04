/**
 * Wanted page test (spec 014 T092).
 *
 * Mocks the read-side query hooks the page composes
 * (useWantedMissing / useWantedCutoff plus the filter
 * lookups). Mutation hooks stay real because they only
 * fire on click — render alone doesn't trigger them.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { WantedPage } from "./index";
import * as wantedQuery from "@/lib/api/queries/wanted";
import * as platformsQuery from "@/lib/api/queries/platforms";
import * as tagsQuery from "@/lib/api/queries/tags";
import * as librariesQuery from "@/lib/api/queries/libraries";

const I18N_BUNDLE = {
  wanted: {
    title: "Wanted",
    tabHint: { missing: "Releases not yet acquired", cutoff: "Below cutoff" },
    tabs: { ariaLabel: "Wanted tabs", missing: "Missing", cutoff: "Cutoff" },
    missing: {
      empty: { title: "Nothing missing", body: "Library complete." },
      loadError: "Failed to load missing releases",
    },
    cutoff: {
      empty: { title: "Cutoff met everywhere", body: "Nothing to upgrade." },
      loadError: "Failed to load cutoff releases",
    },
    search: { label: "Search", placeholder: "Search releases" },
    filters: {
      platform: { label: "Platform", all: "All platforms" },
      tag: { label: "Tag", all: "All tags" },
      library: { label: "Library", all: "All libraries" },
      reset: { label: "Reset", aria: "Reset filters" },
    },
    sort: {
      label: "Sort",
      key: {
        name: "Name",
        created_at: "Added",
        updated_at: "Updated",
        status: "Status",
      },
      direction: { asc: "Ascending", desc: "Descending" },
    },
    bulk: {
      enterSelection: "Select",
      exitSelection: "Cancel selection",
      missingSearch: { idle: "Search missing", pending: "Searching…", success: "Triggered" },
      cutoffSearch: { idle: "Search cutoff", pending: "Searching…", success: "Triggered" },
    },
    fab: {
      missingSearch: "Search missing",
      cutoffSearch: "Search cutoff",
      missingSearchAria: "Trigger missing search",
      cutoffSearchAria: "Trigger cutoff search",
    },
  },
};

function _emptyEnvelope(): ReturnType<typeof wantedQuery.useWantedMissing> {
  return {
    data: {
      page: 1,
      pageSize: 50,
      sortKey: "name",
      sortDirection: "asc",
      totalRecords: 0,
      records: [],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof wantedQuery.useWantedMissing>;
}

function _stubAll(): void {
  vi.spyOn(wantedQuery, "useWantedMissing").mockReturnValue(_emptyEnvelope());
  vi.spyOn(wantedQuery, "useWantedCutoff").mockReturnValue(_emptyEnvelope());
  vi.spyOn(platformsQuery, "usePlatforms").mockReturnValue({
    data: [],
    isSuccess: true,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof platformsQuery.usePlatforms>);
  vi.spyOn(tagsQuery, "useTags").mockReturnValue({
    data: [],
    isSuccess: true,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof tagsQuery.useTags>);
  vi.spyOn(librariesQuery, "useLibraries").mockReturnValue({
    data: [],
    isSuccess: true,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof librariesQuery.useLibraries>);
}

describe("WantedPage", () => {
  it("renders the title and both Missing/Cutoff tabs with Missing active by default", () => {
    _stubAll();

    renderWithProviders(<WantedPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Wanted")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Missing" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Cutoff" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("renders the Missing empty-state when the query returns zero records", () => {
    _stubAll();

    renderWithProviders(<WantedPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Nothing missing")).toBeInTheDocument();
    expect(screen.queryByText("Cutoff met everywhere")).toBeNull();
  });

  it("switches to the Cutoff tab and shows its empty-state on click", async () => {
    _stubAll();
    const user = userEvent.setup();

    renderWithProviders(<WantedPage />, { i18nResources: I18N_BUNDLE });

    await user.click(screen.getByRole("button", { name: "Cutoff" }));

    expect(screen.getByText("Cutoff met everywhere")).toBeInTheDocument();
    expect(screen.queryByText("Nothing missing")).toBeNull();
  });
});
