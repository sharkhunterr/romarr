/**
 * Settings > Content Packs page test (slice 461).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { RomPacksPage } from "./index";
import * as romPacksQuery from "@/lib/api/queries/rom-packs";

const I18N_BUNDLE = {
  settings: {
    romPacks: {
      title: "Content Packs",
      subtitle: "Downloadable ROM archives.",
      loadError: "Couldn't load content packs",
      empty: { title: "No content packs yet", body: "Add a pack above." },
      rowsTitle: "Registered packs",
      rowsHint: "Each pack is downloaded once.",
      addButton: "Add pack",
      platformAny: "Any platform",
      cols: {
        name: "Name",
        platform: "Platform",
        status: "Status",
        results: "Results",
        size: "Size",
        lastIngest: "Last ingest",
        actions: "Actions",
      },
      status: { done: "Done", pending: "Pending" },
      results: { imported: "{{count}} imported" },
      action: {
        ingest: "Ingest",
        reIngest: "Re-ingest",
        running: "Running…",
        edit: "Edit",
        delete: "Delete",
      },
    },
  },
};

function _mockList(
  overrides: Partial<ReturnType<typeof romPacksQuery.useRomPacks>>,
): void {
  vi.spyOn(romPacksQuery, "useRomPacks").mockReturnValue({
    data: undefined,
    isSuccess: false,
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  } as unknown as ReturnType<typeof romPacksQuery.useRomPacks>);
  // The mutations are only invoked on click — a no-op stub is enough.
  const idleMutation = {
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof romPacksQuery.useDeleteRomPack>;
  vi.spyOn(romPacksQuery, "useDeleteRomPack").mockReturnValue(idleMutation);
  vi.spyOn(romPacksQuery, "useIngestRomPack").mockReturnValue(
    idleMutation as unknown as ReturnType<typeof romPacksQuery.useIngestRomPack>,
  );
}

describe("RomPacksPage", () => {
  it("renders the empty-state when useRomPacks returns []", () => {
    _mockList({ data: [], isSuccess: true });

    renderWithProviders(<RomPacksPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Content Packs")).toBeInTheDocument();
    expect(screen.getByText("No content packs yet")).toBeInTheDocument();
  });

  it("surfaces the API error in the EmptyState when the query fails", () => {
    _mockList({
      isError: true,
      error: { message: "rom_pack table missing" } as never,
    });

    renderWithProviders(<RomPacksPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("rom_pack table missing")).toBeInTheDocument();
  });

  it("lists a pack row with its status badge", () => {
    _mockList({
      isSuccess: true,
      data: [
        {
          id: 1,
          name: "No-Intro GBA",
          source_kind: "url",
          url: "https://example.com/gba.zip",
          download_client_id: null,
          download_client_native_id: null,
          platform_id: null,
          platform_slug: null,
          platform_name: null,
          max_size_bytes: null,
          import_mode: "all",
          unknown_action: "triage",
          status: "done",
          downloaded_path: null,
          size_bytes: 1024 ** 3,
          total_files: 3,
          imported_count: 3,
          unmatched_count: 0,
          parked_count: 0,
          failed_count: 0,
          last_error: null,
          last_ingest_at: null,
          created_at: "2026-05-14T00:00:00Z",
          updated_at: "2026-05-14T00:00:00Z",
        },
      ],
    });

    renderWithProviders(<RomPacksPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("No-Intro GBA")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("3 imported")).toBeInTheDocument();
    // A finished pack offers Re-ingest, not the first-run Ingest.
    expect(screen.getByText("Re-ingest")).toBeInTheDocument();
  });
});
