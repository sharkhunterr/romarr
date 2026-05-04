/**
 * Settings > Unidentified page test (spec 014 P-SET).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { UnidentifiedPage } from "./index";
import * as unidentifiedQuery from "@/lib/api/queries/unidentified";

const I18N_BUNDLE = {
  settings: {
    unidentified: {
      title: "Unidentified",
      subtitle: "Dumps awaiting manual matching.",
      empty: { title: "Nothing pending", body: "Library is fully matched." },
    },
  },
};

describe("UnidentifiedPage", () => {
  it("renders the empty-state when useUnidentified returns []", () => {
    vi.spyOn(unidentifiedQuery, "useUnidentified").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof unidentifiedQuery.useUnidentified>);

    renderWithProviders(<UnidentifiedPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Unidentified")).toBeInTheDocument();
    expect(screen.getByText("Nothing pending")).toBeInTheDocument();
  });

  it("surfaces the API error in the EmptyState when the query fails", () => {
    vi.spyOn(unidentifiedQuery, "useUnidentified").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "unidentified table missing" },
    } as unknown as ReturnType<typeof unidentifiedQuery.useUnidentified>);

    renderWithProviders(<UnidentifiedPage />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByText("unidentified table missing"),
    ).toBeInTheDocument();
  });
});
