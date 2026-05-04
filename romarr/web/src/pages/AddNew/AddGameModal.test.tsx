/**
 * AddGameModal tests (spec 014 T074).
 *
 * Verifies the documented contract:
 *   * Renders the candidate's title in the header.
 *   * Submit button fires useAddGameFromLookup.mutate with
 *     the candidate-derived payload + the operator's
 *     platform / monitored picks.
 *   * Submit is disabled while the mutation is pending.
 *   * The Cancel button calls onClose.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { AddGameModal } from "./AddGameModal";
import type { GameLookupRow } from "@/lib/api/queries/lookup";
import * as lookupQuery from "@/lib/api/queries/lookup";
import * as platformsQuery from "@/lib/api/queries/platforms";

const I18N_BUNDLE = {
  addNew: {
    add: {
      modalTitle: "Add {{title}}",
      providerSource: "{{provider}} #{{id}}",
      platformLabel: "Platform",
      loadingPlatforms: "Loading platforms…",
      noPlatforms: "No platforms configured",
      monitoredLabel: "Monitor",
      refreshHint: "Metadata refresh queued.",
      cancel: "Cancel",
      submit: "Add to library",
      submitting: "Adding…",
      successTitle: "Game added",
      successBody: "{{title}} is in the library.",
      errorTitle: "Add failed",
    },
  },
};

const SAMPLE: GameLookupRow = {
  providerName: "igdb",
  providerGameId: "1234",
  title: "Sonic the Hedgehog",
  confidence: 0.95,
  rank: 0,
};

function _stubPlatforms(): void {
  vi.spyOn(platformsQuery, "usePlatforms").mockReturnValue({
    data: [
      { id: 1, name: "Mega Drive", slug: "mega-drive" },
      { id: 2, name: "Super Nintendo", slug: "snes" },
    ],
    isSuccess: true,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof platformsQuery.usePlatforms>);
}

describe("AddGameModal", () => {
  it("renders the candidate's title in the modal header", () => {
    _stubPlatforms();
    vi.spyOn(lookupQuery, "useAddGameFromLookup").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useAddGameFromLookup>);

    renderWithProviders(
      <AddGameModal candidate={SAMPLE} onClose={vi.fn()} />,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("Add Sonic the Hedgehog")).toBeInTheDocument();
    expect(screen.getByText("igdb #1234")).toBeInTheDocument();
  });

  it("fires useAddGameFromLookup.mutate with the candidate-derived payload", () => {
    _stubPlatforms();
    const mutate = vi.fn();
    vi.spyOn(lookupQuery, "useAddGameFromLookup").mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useAddGameFromLookup>);

    renderWithProviders(
      <AddGameModal candidate={SAMPLE} onClose={vi.fn()} />,
      { i18nResources: I18N_BUNDLE },
    );

    // The default platform is the first one (Mega Drive, id=1)
    // per the useEffect default-pick. Click submit with that
    // default + monitored=true.
    fireEvent.click(screen.getByRole("button", { name: "Add to library" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0]?.[0]).toMatchObject({
      providerName: "igdb",
      providerGameId: "1234",
      title: "Sonic the Hedgehog",
      platformId: 1,
      monitored: true,
    });
  });

  it("disables the submit button while the mutation is pending", () => {
    _stubPlatforms();
    vi.spyOn(lookupQuery, "useAddGameFromLookup").mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useAddGameFromLookup>);

    renderWithProviders(
      <AddGameModal candidate={SAMPLE} onClose={vi.fn()} />,
      { i18nResources: I18N_BUNDLE },
    );

    const submit = screen.getByRole("button", { name: "Adding…" });
    expect(submit).toBeDisabled();
  });

  it("calls onClose when the Cancel button is clicked", () => {
    _stubPlatforms();
    vi.spyOn(lookupQuery, "useAddGameFromLookup").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof lookupQuery.useAddGameFromLookup>);
    const onClose = vi.fn();

    renderWithProviders(
      <AddGameModal candidate={SAMPLE} onClose={onClose} />,
      { i18nResources: I18N_BUNDLE },
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
