/**
 * GameDetail page test (spec 014 P-GAME).
 *
 * The page guards two short-circuit branches before any
 * child tab renders: (1) `gameId` not parseable from the
 * URL → `notFound` EmptyState, (2) `useGame` is in error
 * state → `loadError` EmptyState. Both are reachable
 * without navigating into the tabbed body, which keeps the
 * test surface tractable (the full populated path needs
 * router setup + every tab's children mocked, which the
 * tab-level tests own separately).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "@/test/render";

import { GameDetailPage } from "./index";
import * as gamesQuery from "@/lib/api/queries/games";

const I18N_BUNDLE = {
  game: {
    notFound: "Game not found",
    loadError: "Failed to load game",
    delete: { button: "Delete" },
    tabs: {
      ariaLabel: "Game tabs",
      overview: "Overview",
      releases: "Releases",
      history: "History",
      files: "Files",
      notes: "Notes",
    },
  },
};

describe("GameDetailPage", () => {
  it("renders the not-found EmptyState when no :gameId is in the URL", () => {
    vi.spyOn(gamesQuery, "useGame").mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof gamesQuery.useGame>);

    renderWithProviders(<GameDetailPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Game not found")).toBeInTheDocument();
  });

  it("renders the loadError EmptyState when useGame fails", () => {
    vi.spyOn(gamesQuery, "useGame").mockReturnValue({
      data: undefined,
      isLoading: false,
      isPending: false,
      isError: true,
      isSuccess: false,
      error: { message: "game db unreachable" },
    } as unknown as ReturnType<typeof gamesQuery.useGame>);

    renderWithProviders(
      <Routes>
        <Route path="/game/:gameId" element={<GameDetailPage />} />
      </Routes>,
      {
        i18nResources: I18N_BUNDLE,
        routerEntries: ["/game/42"],
      },
    );

    expect(screen.getByText("Failed to load game")).toBeInTheDocument();
    expect(screen.getByText("game db unreachable")).toBeInTheDocument();
  });
});
