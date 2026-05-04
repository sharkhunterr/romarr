/**
 * AddNew page test (spec 014 P-ADD).
 *
 * Default route loads with no `?q=` so the empty-state copy
 * renders. A populated lookup query produces one row per
 * candidate with the documented Add button. RecentAdditions
 * stays mocked to its loading branch so the section header
 * renders without firing /games.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { AddNewPage } from "./index";
import * as lookupQuery from "@/lib/api/queries/lookup";
import * as gamesQuery from "@/lib/api/queries/games";
import * as platformsQuery from "@/lib/api/queries/platforms";

const I18N_BUNDLE = {
  addNew: {
    title: "Add new",
    subtitle: "Search every metadata provider.",
    search: { label: "Lookup query", placeholder: "Title or alias" },
    empty: { title: "Start typing", body: "We'll search every provider." },
    noResults: "No matches for {{q}}",
    loadError: "Lookup failed",
    addButton: "Add",
    addHint: "Adding queues a metadata refresh.",
    recent: { title: "Recent additions", loading: "Loading recent additions…" },
  },
};

function _stubGames(): void {
  vi.spyOn(gamesQuery, "useGames").mockReturnValue({
    data: undefined,
    isPending: true,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof gamesQuery.useGames>);
  vi.spyOn(platformsQuery, "usePlatformsById").mockReturnValue(new Map());
}

describe("AddNewPage", () => {
  it("renders the empty-state copy when no query is set", () => {
    vi.spyOn(lookupQuery, "useGameLookup").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useGameLookup>);
    _stubGames();

    renderWithProviders(<AddNewPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Add new")).toBeInTheDocument();
    expect(screen.getByText("Start typing")).toBeInTheDocument();
    expect(
      screen.getByText("We'll search every provider."),
    ).toBeInTheDocument();
  });

  it("renders one row per candidate when the lookup returns data", () => {
    vi.spyOn(lookupQuery, "useGameLookup").mockReturnValue({
      data: [
        {
          providerName: "igdb",
          providerGameId: "1234",
          title: "Sonic the Hedgehog",
          confidence: 0.95,
        },
        {
          providerName: "screenscraper",
          providerGameId: "abc",
          title: "Sonic the Hedgehog 2",
          confidence: 0.65,
        },
      ],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useGameLookup>);
    _stubGames();

    renderWithProviders(<AddNewPage />, {
      i18nResources: I18N_BUNDLE,
      routerEntries: ["/?q=sonic"],
    });

    expect(screen.getByText("Sonic the Hedgehog")).toBeInTheDocument();
    expect(screen.getByText("Sonic the Hedgehog 2")).toBeInTheDocument();
    // One Add button per row.
    expect(screen.getAllByRole("button", { name: "Add" })).toHaveLength(2);
  });

  it("surfaces the lookup error when the query fails", () => {
    vi.spyOn(lookupQuery, "useGameLookup").mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: { message: "provider unreachable" },
    } as unknown as ReturnType<typeof lookupQuery.useGameLookup>);
    _stubGames();

    renderWithProviders(<AddNewPage />, {
      i18nResources: I18N_BUNDLE,
      routerEntries: ["/?q=mario"],
    });

    expect(screen.getByText("Lookup failed")).toBeInTheDocument();
    expect(screen.getByText("provider unreachable")).toBeInTheDocument();
  });
});
