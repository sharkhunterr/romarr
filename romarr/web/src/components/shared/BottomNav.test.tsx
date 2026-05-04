/**
 * BottomNav test (spec 014 T015).
 *
 * The contract is the five documented entries (Library /
 * Wanted / Activity / Settings / Search) rendering with the
 * mobile-only ``md:hidden`` class. Each route entry is a
 * NavLink to its documented path; the Search entry is a
 * button that opens the global ⌘+K palette via
 * ``useSearchStore.openModal``.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { BottomNav } from "./BottomNav";
import * as searchStore from "@/lib/store/search";

const I18N_BUNDLE = {
  translation: {
    nav: {
      library: "Library",
      wanted: "Wanted",
      activity: "Activity",
      settings: "Settings",
      search: "Search",
      primary: "Primary",
    },
  },
};

describe("BottomNav", () => {
  it("renders the five documented entries with the mobile-only class", () => {
    renderWithProviders(<BottomNav />, { i18nResources: I18N_BUNDLE });

    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav.className).toContain("md:hidden");

    expect(
      screen.getByRole("link", { name: /Library/i }),
    ).toHaveAttribute("href", "/library");
    expect(
      screen.getByRole("link", { name: /Wanted/i }),
    ).toHaveAttribute("href", "/wanted");
    expect(
      screen.getByRole("link", { name: /Activity/i }),
    ).toHaveAttribute("href", "/activity");
    expect(
      screen.getByRole("link", { name: /Settings/i }),
    ).toHaveAttribute("href", "/settings");
    expect(
      screen.getByRole("button", { name: /Search/i }),
    ).toBeInTheDocument();
  });

  it("opens the global ⌘+K palette when the Search entry is clicked", async () => {
    const openModal = vi.fn();
    vi.spyOn(searchStore, "useSearchStore").mockImplementation(
      ((selector: (s: { openModal: () => void }) => unknown) =>
        selector({ openModal })) as unknown as typeof searchStore.useSearchStore,
    );

    const user = userEvent.setup();
    renderWithProviders(<BottomNav />, { i18nResources: I18N_BUNDLE });

    await user.click(screen.getByRole("button", { name: /Search/i }));

    expect(openModal).toHaveBeenCalledTimes(1);
  });
});
