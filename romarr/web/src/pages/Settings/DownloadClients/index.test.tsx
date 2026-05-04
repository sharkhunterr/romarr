/**
 * Settings > Download clients page test (spec 014 P-SET).
 *
 * Three documented states: loading skeleton, empty-state
 * (zero clients), error banner (query failed). The list /
 * search-and-filter path is covered by DownloadClientRow's
 * dedicated tests when they ship.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { DownloadClientsPage } from "./index";
import * as downloadClientsQuery from "@/lib/api/queries/download-clients";

const I18N_BUNDLE = {
  settings: {
    downloadClients: {
      title: "Download clients",
      subtitle: "Where Romarr hands grabs.",
      empty: {
        title: "No download clients yet",
        body: "Add qBittorrent or SABnzbd to get started.",
      },
      search: {
        label: "Search clients",
        placeholder: "Name or host",
        noMatches: "No clients matching your filter.",
      },
    },
  },
};

describe("DownloadClientsPage", () => {
  it("renders the empty-state when useDownloadClients returns []", () => {
    vi.spyOn(downloadClientsQuery, "useDownloadClients").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof downloadClientsQuery.useDownloadClients>);

    renderWithProviders(<DownloadClientsPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("Download clients")).toBeInTheDocument();
    expect(screen.getByText("No download clients yet")).toBeInTheDocument();
    expect(
      screen.getByText("Add qBittorrent or SABnzbd to get started."),
    ).toBeInTheDocument();
  });

  it("surfaces the API error in the empty-state when the query fails", () => {
    vi.spyOn(downloadClientsQuery, "useDownloadClients").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "downloadclient table missing" },
    } as unknown as ReturnType<typeof downloadClientsQuery.useDownloadClients>);

    renderWithProviders(<DownloadClientsPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("No download clients yet")).toBeInTheDocument();
    expect(
      screen.getByText("downloadclient table missing"),
    ).toBeInTheDocument();
  });

  it("renders the loading skeleton while the query is pending", () => {
    vi.spyOn(downloadClientsQuery, "useDownloadClients").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: true,
      isPending: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof downloadClientsQuery.useDownloadClients>);

    renderWithProviders(<DownloadClientsPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("Download clients")).toBeInTheDocument();
    // Skeleton renders aria-hidden divs; we just confirm we
    // didn't accidentally fall through to one of the three
    // "settled" states.
    expect(screen.queryByText("No download clients yet")).toBeNull();
  });
});
