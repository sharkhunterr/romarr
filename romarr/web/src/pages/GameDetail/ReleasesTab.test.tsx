/**
 * ReleasesTab tests (spec 014 T080 multi-disc accordion).
 *
 * Verifies the slice 249 multi-disc grouping: Releases with
 * ``parent_release_id`` are folded under their parent's
 * ``MultiDiscAccordion``; sibling releases (no parent) render
 * as flat rows. Plus the empty-state and loadError branches
 * for completeness.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { ReleasesTab } from "./ReleasesTab";
import * as gamesQuery from "@/lib/api/queries/games";

const I18N_BUNDLE = {
  game: {
    releases: {
      loadError: "Couldn't load releases",
      empty: { title: "No releases yet", body: "—" },
      monitor: { on: "Monitored", off: "Paused" },
      multiDiscTitle: "{{title}} — {{total}} discs",
    },
  },
};

function _stubReleases(
  data: gamesQuery.Release[] | undefined,
  state: "success" | "error" | "loading",
): void {
  vi.spyOn(gamesQuery, "useReleasesForGame").mockReturnValue({
    data,
    isLoading: state === "loading",
    isError: state === "error",
    isSuccess: state === "success",
    error: state === "error" ? { message: "boom" } : null,
  } as unknown as ReturnType<typeof gamesQuery.useReleasesForGame>);
  vi.spyOn(gamesQuery, "useToggleReleaseMonitor").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof gamesQuery.useToggleReleaseMonitor>);
}

function _release(
  overrides: Partial<gamesQuery.Release>,
): gamesQuery.Release {
  return {
    id: 1,
    game_id: 100,
    name: "Sample Release",
    regions: ["USA"],
    languages: ["en"],
    revision: null,
    dump_status: "verified",
    naming_convention: "no-intro",
    status: "imported",
    monitored: true,
    cutoff_met: false,
    disc_number: 1,
    disc_total: 1,
    parent_release_id: null,
    library_id: null,
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
    ...overrides,
  } as unknown as gamesQuery.Release;
}

describe("ReleasesTab", () => {
  it("renders the empty-state when useReleasesForGame returns []", () => {
    _stubReleases([], "success");

    renderWithProviders(
      <ReleasesTab gameId={100} platformId={1} />,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("No releases yet")).toBeInTheDocument();
  });

  it("renders the loadError EmptyState when the query fails", () => {
    _stubReleases(undefined, "error");

    renderWithProviders(
      <ReleasesTab gameId={100} platformId={1} />,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("Couldn't load releases")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("groups multi-disc releases under a MultiDiscAccordion (T080)", () => {
    // 3-disc fixture: parent (disc 1) + 2 children (discs 2, 3).
    const parent = _release({
      id: 100,
      name: "Final Fantasy IX (USA)",
      disc_number: 1,
      disc_total: 3,
    });
    const disc2 = _release({
      id: 101,
      name: "Final Fantasy IX (USA) (Disc 2)",
      disc_number: 2,
      disc_total: 3,
      parent_release_id: 100,
    });
    const disc3 = _release({
      id: 102,
      name: "Final Fantasy IX (USA) (Disc 3)",
      disc_number: 3,
      disc_total: 3,
      parent_release_id: 100,
    });
    _stubReleases([disc3, parent, disc2], "success");

    renderWithProviders(
      <ReleasesTab gameId={100} platformId={1} />,
      { i18nResources: I18N_BUNDLE },
    );

    // The accordion summary carries the documented multi-disc
    // title interpolation ("Title — N discs").
    expect(
      screen.getByText("Final Fantasy IX (USA) — 3 discs"),
    ).toBeInTheDocument();
  });

  it("renders single-disc releases as flat rows (no accordion)", () => {
    _stubReleases(
      [_release({ id: 1, name: "Sonic the Hedgehog (USA)" })],
      "success",
    );

    renderWithProviders(
      <ReleasesTab gameId={100} platformId={1} />,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("Sonic the Hedgehog (USA)")).toBeInTheDocument();
    // No accordion summary for single-disc releases.
    expect(
      screen.queryByText(/— \d+ discs/),
    ).toBeNull();
  });
});
