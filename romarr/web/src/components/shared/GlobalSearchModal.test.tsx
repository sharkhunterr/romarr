/**
 * GlobalSearchModal tests (spec 014 T110 + T111).
 *
 * T110: useGlobalSearchHotkey toggles the modal on Ctrl+K /
 * Cmd+K. Tested by mounting a tiny harness that calls the
 * hook + dispatching synthetic KeyboardEvent on window.
 *
 * T111: the modal renders three documented result groups —
 * Recent searches (when query is empty), Settings (matches
 * SETTINGS_NAV_ENTRIES on slug + i18n label), Games (placeholder
 * until backend ships, queries useGames when query is non-empty).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { GlobalSearchModal, useGlobalSearchHotkey } from "./GlobalSearchModal";
import { useSearchStore } from "@/lib/store/search";
import * as gamesQuery from "@/lib/api/queries/games";

const I18N_BUNDLE = {
  search: {
    placeholder: "Type to search…",
    title: "Search",
    open: "Open search (⌘K)",
    sectionRecent: "Recent",
    sectionSettings: "Settings",
    sectionGames: "Games",
    empty: "Start typing.",
    noResults: "Nothing matches.",
    clearRecent: "Clear recent",
  },
  settings: {
    nav: {
      profiles: "Profiles",
      "media-management": "Media management",
      "quality-definitions": "Quality definitions",
      indexers: "Indexers",
      "download-clients": "Download clients",
      "dat-sources": "DAT sources",
      "metadata-sources": "Metadata sources",
      platforms: "Platforms",
      connect: "Notifications",
      tags: "Tags",
      unidentified: "Unidentified",
      ui: "User interface",
      general: "General",
    },
  },
};

afterEach(() => {
  // Reset store so per-test state doesn't leak.
  useSearchStore.getState().clearRecent();
  useSearchStore.getState().closeModal();
});

function HotkeyHarness(): null {
  useGlobalSearchHotkey();
  return null;
}

describe("useGlobalSearchHotkey (T110)", () => {
  it("toggles the modal on Ctrl+K", () => {
    renderWithProviders(<HotkeyHarness />, { i18nResources: I18N_BUNDLE });

    expect(useSearchStore.getState().open).toBe(false);

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "k", ctrlKey: true }),
      );
    });
    expect(useSearchStore.getState().open).toBe(true);

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "k", ctrlKey: true }),
      );
    });
    expect(useSearchStore.getState().open).toBe(false);
  });

  it("toggles on Cmd+K (mac path)", () => {
    renderWithProviders(<HotkeyHarness />, { i18nResources: I18N_BUNDLE });

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "k", metaKey: true }),
      );
    });
    expect(useSearchStore.getState().open).toBe(true);
  });

  it("ignores other keys", () => {
    renderWithProviders(<HotkeyHarness />, { i18nResources: I18N_BUNDLE });

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "k" }));
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "j", ctrlKey: true }),
      );
    });
    expect(useSearchStore.getState().open).toBe(false);
  });
});

describe("GlobalSearchModal grouping (T111)", () => {
  it("returns null when the modal is closed", () => {
    vi.spyOn(gamesQuery, "useGames").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gamesQuery.useGames>);

    const { container } = renderWithProviders(<GlobalSearchModal />, {
      i18nResources: I18N_BUNDLE,
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the Settings group with matching entries when typing", () => {
    vi.spyOn(gamesQuery, "useGames").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gamesQuery.useGames>);

    act(() => {
      useSearchStore.getState().openModal();
    });

    renderWithProviders(<GlobalSearchModal />, { i18nResources: I18N_BUNDLE });

    const input = screen.getByPlaceholderText("Type to search…");
    fireEvent.change(input, { target: { value: "tags" } });

    // The "Tags" settings entry should appear in the result list.
    expect(screen.getByText("Tags")).toBeInTheDocument();
  });

  it("renders the Recent group when the query is empty (after pushing entries)", () => {
    vi.spyOn(gamesQuery, "useGames").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof gamesQuery.useGames>);

    act(() => {
      useSearchStore.getState().pushRecent("Sonic");
      useSearchStore.getState().pushRecent("Mario");
      useSearchStore.getState().openModal();
    });

    renderWithProviders(<GlobalSearchModal />, { i18nResources: I18N_BUNDLE });

    // Both pushed queries surface in the recent group when input
    // is empty.
    expect(screen.getByText("Sonic")).toBeInTheDocument();
    expect(screen.getByText("Mario")).toBeInTheDocument();
  });
});
