/**
 * QueueList row tests — explicit Remove button + swipe-to-remove
 * (spec 014 T092).
 *
 * jsdom can't fully simulate native pointer drags, so the swipe
 * test asserts the row carries the expected gesture wiring
 * (data-swipe attribute + initial offset). The threshold-crossing
 * trigger lives at the E2E layer when Playwright lands.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";
import * as queueQuery from "@/lib/api/queries/queue";
import * as downloadClientsQuery from "@/lib/api/queries/download-clients";

import { QueueList } from "./QueueList";

const I18N_BUNDLE = {
  activity: {
    queue: {
      empty: { title: "Queue is empty", body: "Nothing downloading." },
      filter: {
        all: "All",
        downloading: "Downloading",
        completed: "Completed",
        failed: "Failed",
        paused: "Paused",
        queued: "Queued",
      },
      remove: "Remove",
      removing: "Removing…",
      removeAria: "Remove {{id}}",
      removeConfirm: "Remove this download?",
      subtitle: "release={{releaseId}} client={{clientId}}",
      attempt: " (attempt {{count}})",
      progressLabel: "{{pct}}% complete",
      size: "{{value}}",
      eta: "ETA {{value}}",
      etaUnknown: "—",
      removeFailedFallback: "Remove failed",
    },
  },
};

const SAMPLE_ENTRY: queueQuery.QueueEntry = {
  id: 1,
  releaseId: 42,
  downloadClientId: 1,
  downloadClientNativeId: "info-hash-deadbeef",
  state: "downloading" as queueQuery.QueueState,
  progress: 0.6,
  sizeBytes: 1024 * 1024,
  etaSeconds: 60,
  errorMsg: null,
  attemptCount: 0,
  lastUpdatedAt: "2026-05-01T00:00:00Z",
};

beforeEach(() => {
  vi.spyOn(queueQuery, "useQueue").mockReturnValue({
    data: {
      page: 1,
      pageSize: 50,
      sortKey: "last_updated_at",
      sortDirection: "desc",
      totalRecords: 1,
      records: [SAMPLE_ENTRY],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queueQuery.useQueue>);
  vi.spyOn(downloadClientsQuery, "useDownloadClientsById").mockReturnValue(
    new Map([[1, { id: 1, name: "qBit" } as unknown as never]]),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("QueueList row", () => {
  it("renders the row with a Remove button", () => {
    renderWithProviders(<QueueList />, { i18nResources: I18N_BUNDLE });
    const removeButton = screen.getByRole("button", {
      name: /Remove info-hash-deadbeef/,
    });
    expect(removeButton).toBeInTheDocument();
  });

  it("wires the swipe-to-remove gesture (data-swipe attribute idle)", () => {
    const { container } = renderWithProviders(<QueueList />, {
      i18nResources: I18N_BUNDLE,
    });
    // The <li> root carries the data-swipe attribute that the
    // swipe gesture flips between idle / active. Initial state is
    // idle (no offset).
    const row = container.querySelector("li[data-swipe]") as HTMLElement;
    expect(row).toBeTruthy();
    expect(row.getAttribute("data-swipe")).toBe("idle");
  });
});
