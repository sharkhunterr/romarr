/**
 * Settings > Media Management page test (spec 014 P-SET).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { MediaManagementPage } from "./index";
import * as librariesQuery from "@/lib/api/queries/libraries";

const I18N_BUNDLE = {
  settings: {
    mediaManagement: {
      title: "Media management",
      subtitle: "Library roots + naming + hardlinks.",
      empty: { title: "No libraries", body: "Add a library to get started." },
      editorHint: "Library editor lands in a follow-up slice.",
    },
  },
};

describe("MediaManagementPage", () => {
  it("renders the empty-state when useLibraries returns []", () => {
    vi.spyOn(librariesQuery, "useLibraries").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof librariesQuery.useLibraries>);

    renderWithProviders(<MediaManagementPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("Media management")).toBeInTheDocument();
    expect(screen.getByText("No libraries")).toBeInTheDocument();
    expect(
      screen.getByText("Add a library to get started."),
    ).toBeInTheDocument();
  });

  it("surfaces the API error in the EmptyState when the query fails", () => {
    vi.spyOn(librariesQuery, "useLibraries").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "library table missing" },
    } as unknown as ReturnType<typeof librariesQuery.useLibraries>);

    renderWithProviders(<MediaManagementPage />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByText("library table missing")).toBeInTheDocument();
  });
});
