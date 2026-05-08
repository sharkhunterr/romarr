/**
 * OverviewTab tests (spec 014 T078 + T079).
 *
 * Two contracts:
 *   * Edit-in-place — click ✎ on the title; the inline input
 *     renders with the current value; pressing Enter fires
 *     ``useEditGameField.mutate`` with the typed value.
 *   * Field lock — click the 🔒/🔓 toggle next to a known
 *     ProviderField; ``useToggleFieldLock.mutate`` is called
 *     with the inverted ``locked`` flag.
 *
 * The tab pulls from many hooks; we stub each so render is
 * deterministic. The test uses fireEvent (synchronous) rather
 * than userEvent so the in-component setTimeout-based focus
 * doesn't fight with fake timers.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { GameHeader } from "./GameHeader";
import { OverviewTab } from "./OverviewTab";
import * as gamesQuery from "@/lib/api/queries/games";
import * as platformsQuery from "@/lib/api/queries/platforms";
import * as tagsQuery from "@/lib/api/queries/tags";

const I18N_BUNDLE = {
  game: {
    overview: {
      cover: { changeAria: "Change cover", changeShort: "Change" },
      lock: {
        lockAria: "Lock {{field}}",
        unlockAria: "Unlock {{field}}",
        lockedHint: "Locked",
      },
      edit: {
        openAria: "Edit {{field}}",
        save: "Save",
        cancel: "Cancel",
        titleAria: "Title input",
        summaryAria: "Summary input",
        errorTitle: "Edit failed",
      },
      summary: { empty: "No summary." },
      fields: {
        title: "Title",
        developer: "Developer",
        publisher: "Publisher",
        releaseDate: "Release date",
        platform: "Platform",
        rating: "Rating",
        ageRating: "Age rating",
        genres: "Genres",
        playerCount: "Players",
        howLongToBeat: "HLTB",
      },
      refresh: { button: "Refresh", refreshing: "Refreshing…", aria: "Refresh metadata" },
      monitor: { on: "Monitored", off: "Paused", toggleAria: "Toggle monitor" },
      tags: { label: "Tags", manage: "Manage tags" },
    },
  },
};

function _baseGame(): gamesQuery.Game {
  return {
    id: 42,
    platform_id: 1,
    title: "Sonic the Hedgehog",
    slug: "sonic-the-hedgehog",
    summary: "A hedgehog runs fast.",
    developer: "Sonic Team",
    publisher: "Sega",
    release_date: "1991-06-23",
    rating: 9.1,
    age_rating: "E",
    genres: ["platformer"],
    monitored: true,
    needs_metadata_refresh: false,
    cover_path: null,
    locked_fields: [],
    tags: [],
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  } as unknown as gamesQuery.Game;
}

function _stubAll(): {
  edit: ReturnType<typeof vi.fn>;
  toggleLock: ReturnType<typeof vi.fn>;
} {
  const edit = vi.fn();
  const toggleLock = vi.fn();

  vi.spyOn(gamesQuery, "useEditGameField").mockReturnValue({
    mutate: edit,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof gamesQuery.useEditGameField>);
  vi.spyOn(gamesQuery, "useToggleFieldLock").mockReturnValue({
    mutate: toggleLock,
    isPending: false,
  } as unknown as ReturnType<typeof gamesQuery.useToggleFieldLock>);
  vi.spyOn(gamesQuery, "useRefreshGameMetadata").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof gamesQuery.useRefreshGameMetadata>);
  vi.spyOn(gamesQuery, "useToggleGameMonitor").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof gamesQuery.useToggleGameMonitor>);
  vi.spyOn(platformsQuery, "usePlatformsById").mockReturnValue(
    new Map(),
  );
  vi.spyOn(tagsQuery, "useTagsById").mockReturnValue(new Map());

  return { edit, toggleLock };
}

describe("OverviewTab", () => {
  it("edit-in-place on the title fires useEditGameField.mutate (T078)", () => {
    const { edit } = _stubAll();

    // Slice 364: title editing now lives in GameHeader (cover +
    // title + summary moved out of OverviewTab to make room for
    // the tab bar to slide below the header). The contract
    // — click ✎ → input → Enter fires useEditGameField.mutate
    // — is unchanged.
    renderWithProviders(
      <GameHeader
        game={_baseGame()}
        onSearchClick={() => undefined}
        onDeleteClick={() => undefined}
      />,
      { i18nResources: I18N_BUNDLE },
    );

    // Click the ✎ pencil next to the title to enter editing mode.
    fireEvent.click(screen.getByRole("button", { name: "Edit Title" }));

    // The inline input lands carrying the current title.
    const input = screen.getByLabelText("Title input") as HTMLInputElement;
    expect(input.value).toBe("Sonic the Hedgehog");

    // Type a new title and press Enter to commit.
    fireEvent.change(input, { target: { value: "Sonic the Hedgehog (USA)" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(edit).toHaveBeenCalledTimes(1);
    expect(edit.mock.calls[0]?.[0]).toEqual({
      gameId: 42,
      field: "title",
      value: "Sonic the Hedgehog (USA)",
    });
  });

  it("clicking the title lock button fires useToggleFieldLock.mutate (T079)", () => {
    const { toggleLock } = _stubAll();

    renderWithProviders(<OverviewTab game={_baseGame()} />, {
      i18nResources: I18N_BUNDLE,
    });

    // The "release_date" FactRow has a known ProviderField so it
    // exposes a FieldLockButton with the documented aria-label.
    fireEvent.click(
      screen.getByRole("button", { name: "Lock release_date" }),
    );

    expect(toggleLock).toHaveBeenCalledTimes(1);
    expect(toggleLock.mock.calls[0]?.[0]).toEqual({
      gameId: 42,
      field: "release_date",
      locked: true,
    });
  });

  it("re-clicking a locked field flips locked=false (T079)", () => {
    const { toggleLock } = _stubAll();
    const game = _baseGame();
    (game as unknown as { locked_fields: string[] }).locked_fields = [
      "release_date",
    ];

    renderWithProviders(<OverviewTab game={game} />, {
      i18nResources: I18N_BUNDLE,
    });

    // Locked field exposes "Unlock" instead of "Lock".
    fireEvent.click(
      screen.getByRole("button", { name: "Unlock release_date" }),
    );

    expect(toggleLock).toHaveBeenCalledTimes(1);
    expect(toggleLock.mock.calls[0]?.[0]).toEqual({
      gameId: 42,
      field: "release_date",
      locked: false,
    });
  });
});
