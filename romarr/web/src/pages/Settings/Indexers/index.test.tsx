/**
 * Settings > Indexers page test (spec 014 P-SET).
 *
 * The page composes ApplicationsPanel above the list. Mocks
 * stub useIndexers (page) + useApplications +
 * useCurrentPrincipal (panel) so render is deterministic.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { IndexersPage } from "./index";
import * as indexersQuery from "@/lib/api/queries/indexers";
import * as applicationsQuery from "@/lib/api/queries/applications";
import * as authQuery from "@/lib/api/queries/auth";

const I18N_BUNDLE = {
  settings: {
    indexers: {
      title: "Indexers",
      subtitle: "Newznab + Torznab sources.",
      empty: { title: "No indexers", body: "Hook up Prowlarr to get started." },
      search: {
        label: "Search indexers",
        placeholder: "Name or URL",
        noMatches: "Nothing matches.",
      },
      applications: {
        title: "Prowlarr applications",
        empty: "No Prowlarr instances registered.",
        unregisterConfirm: "Unregister {{name}}?",
        unregister: "Unregister",
        ariaLabel: "Prowlarr applications",
      },
    },
  },
};

function _stubApplications(): void {
  vi.spyOn(applicationsQuery, "useApplications").mockReturnValue({
    data: [],
    isSuccess: true,
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof applicationsQuery.useApplications>);
  vi.spyOn(applicationsQuery, "useDeleteApplication").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof applicationsQuery.useDeleteApplication>);
  vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
    data: { kind: "user", role: "admin", username: "alice" },
    isSuccess: true,
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);
}

describe("IndexersPage", () => {
  it("renders the empty-state when useIndexers returns []", () => {
    vi.spyOn(indexersQuery, "useIndexers").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof indexersQuery.useIndexers>);
    _stubApplications();

    renderWithProviders(<IndexersPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Indexers")).toBeInTheDocument();
    expect(screen.getByText("No indexers")).toBeInTheDocument();
  });

  it("surfaces the API error when useIndexers fails", () => {
    vi.spyOn(indexersQuery, "useIndexers").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "indexer table missing" },
    } as unknown as ReturnType<typeof indexersQuery.useIndexers>);
    _stubApplications();

    renderWithProviders(<IndexersPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("indexer table missing")).toBeInTheDocument();
  });
});
