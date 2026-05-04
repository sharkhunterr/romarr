/**
 * Activity page test (spec 014 T093).
 *
 * Covers the Queue ↔ History tab routing exposed by the
 * page itself plus the empty-state copy each child list
 * surfaces. Hooks are mocked individually because the
 * children make their own queries (Queue → useQueue +
 * useDownloadClientsById, History → useHistory).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { ActivityPage } from "./index";
import * as queueQuery from "@/lib/api/queries/queue";
import * as downloadClientsQuery from "@/lib/api/queries/download-clients";
import * as systemQuery from "@/lib/api/queries/system";

const I18N_BUNDLE = {
  activity: {
    title: "Activity",
    tabHint: { queue: "Live downloads", history: "Audit trail" },
    tabs: { ariaLabel: "Activity tabs", queue: "Queue", history: "History" },
    queue: {
      empty: { title: "Queue is empty", body: "Nothing downloading." },
    },
    history: {
      empty: { title: "History is empty", body: "No events yet." },
    },
  },
};

function _mockEmptyQueue(): void {
  vi.spyOn(queueQuery, "useQueue").mockReturnValue({
    data: {
      page: 1,
      pageSize: 50,
      sortKey: "last_updated_at",
      sortDirection: "desc",
      totalRecords: 0,
      records: [],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queueQuery.useQueue>);
  vi.spyOn(downloadClientsQuery, "useDownloadClientsById").mockReturnValue(
    new Map(),
  );
}

function _mockEmptyHistory(): void {
  vi.spyOn(systemQuery, "useHistory").mockReturnValue({
    data: {
      page: 1,
      pageSize: 50,
      sortKey: "date",
      sortDirection: "desc",
      totalRecords: 0,
      records: [],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof systemQuery.useHistory>);
}

describe("ActivityPage", () => {
  it("renders the title and both tab buttons with Queue active by default", () => {
    _mockEmptyQueue();
    _mockEmptyHistory();

    renderWithProviders(<ActivityPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Activity")).toBeInTheDocument();
    const queueTab = screen.getByRole("button", { name: "Queue" });
    const historyTab = screen.getByRole("button", { name: "History" });
    expect(queueTab).toHaveAttribute("aria-pressed", "true");
    expect(historyTab).toHaveAttribute("aria-pressed", "false");
  });

  it("renders the Queue empty-state when no downloads are queued", () => {
    _mockEmptyQueue();
    _mockEmptyHistory();

    renderWithProviders(<ActivityPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Queue is empty")).toBeInTheDocument();
    expect(screen.queryByText("History is empty")).toBeNull();
  });

  it("switches to the History tab when the History button is clicked", async () => {
    _mockEmptyQueue();
    _mockEmptyHistory();
    const user = userEvent.setup();

    renderWithProviders(<ActivityPage />, { i18nResources: I18N_BUNDLE });

    await user.click(screen.getByRole("button", { name: "History" }));

    expect(screen.getByText("History is empty")).toBeInTheDocument();
    expect(screen.queryByText("Queue is empty")).toBeNull();
    expect(screen.getByRole("button", { name: "History" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
