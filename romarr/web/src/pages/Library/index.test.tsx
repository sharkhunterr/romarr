/**
 * Library page test (spec 014 P-LIB).
 *
 * Mocks the read-side hooks the page composes (`useGames`
 * for the grid; `usePlatforms` / `useTags` / `useLibraries`
 * for the filter selects). Mutation hooks stay real because
 * render alone never fires them.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { LibraryPage } from "./index";
import * as gamesQuery from "@/lib/api/queries/games";
import * as platformsQuery from "@/lib/api/queries/platforms";
import * as tagsQuery from "@/lib/api/queries/tags";
import * as librariesQuery from "@/lib/api/queries/libraries";

const I18N_BUNDLE = {
  library: {
    title: "Library",
    subtitle: "Every monitored game.",
    count_one: "{{count}} game",
    count_other: "{{count}} games",
    search: { label: "Search", placeholder: "Title or alias" },
    filters: {
      platform: { label: "Platform", all: "All platforms" },
      tag: { label: "Tag", all: "All tags" },
      library: { label: "Library", all: "All libraries" },
      monitoredOnly: { on: "Monitored only", off: "All games" },
      reset: { label: "Reset", aria: "Reset filters" },
    },
    sort: {
      label: "Sort by",
      key: {
        title: "Title",
        added_at: "Added",
        release_date: "Released",
        rating: "Rating",
      },
      direction: { asc: "Ascending", desc: "Descending" },
    },
    bulk: {
      enterSelection: "Select",
      exitSelection: "Cancel",
      toolbarAria: "Bulk toolbar",
      selectedCount: "{{count}} selected",
      selectAll: "Select all",
      monitor: { label: "Monitor", pending: "Updating…" },
      unmonitor: { label: "Unmonitor", pending: "Updating…" },
    },
    loadError: "Library unavailable",
    empty: {
      title: "No games yet",
      body: "Click + to add your first game.",
    },
    noResults: {
      title: "No matches",
      body: 'No games matching "{{q}}".',
    },
    fab: { add: "Add", addAria: "Add a new game" },
  },
};

function _stubFilters(): void {
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

describe("LibraryPage", () => {
  it("renders the title + Add FAB and the documented empty-state", () => {
    vi.spyOn(gamesQuery, "useGames").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gamesQuery.useGames>);
    _stubFilters();

    renderWithProviders(<LibraryPage />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByRole("heading", { name: "Library" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No games yet")).toBeInTheDocument();
    // FAB has aria-label "Add a new game".
    expect(
      screen.getByLabelText("Add a new game"),
    ).toBeInTheDocument();
  });

  it("surfaces the API error in an EmptyState when the query fails", () => {
    vi.spyOn(gamesQuery, "useGames").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "library db down" },
    } as unknown as ReturnType<typeof gamesQuery.useGames>);
    _stubFilters();

    renderWithProviders(<LibraryPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Library unavailable")).toBeInTheDocument();
    expect(screen.getByText("library db down")).toBeInTheDocument();
  });
});
