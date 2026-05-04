/**
 * IndexerRow tests (spec 014 T098).
 *
 * Three branches of the row's behaviour:
 *   * Test button fires the useTestIndexer mutation with the
 *     row's id; the result is rendered inline.
 *   * Test failure surfaces the error message in a role=alert
 *     paragraph.
 *   * Delete button opens the confirm panel; clicking the
 *     confirm pill fires useDeleteIndexer with the row's id.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { IndexerRow } from "./IndexerRow";
import * as indexersQuery from "@/lib/api/queries/indexers";

const I18N_BUNDLE = {
  settings: {
    indexers: {
      rss: "RSS",
      auto: "Auto",
      interactive: "Interactive",
      health: {
        ok: "Healthy",
        auth: "Auth failed",
        protocol: "Protocol error",
        connectivity: "Unreachable",
        circuit_open: "Circuit open",
        untested: "Not tested",
      },
      source: { manual: "Manual", prowlarr: "Prowlarr" },
      test: {
        button: "Test",
        running: "Testing…",
        successCaps: "OK",
        successSearch: "search OK",
        failure: "{{message}}",
      },
      delete: {
        button: "Delete",
        confirm: "Confirm delete",
        cancel: "Cancel",
        confirmTitle: "Delete indexer?",
        confirmBody: "Remove {{name}} permanently?",
      },
      toggle: { errorFallback: "toggle failed" },
    },
  },
};

const SAMPLE: indexersQuery.Indexer = {
  id: 7,
  name: "Acme Newznab",
  source: "manual",
  implementation: "newznab",
  url: "https://acme.test",
  enable_rss: true,
  enable_automatic_search: true,
  enable_interactive_search: false,
  last_health_at: null,
  last_health_ok: null,
  last_health_error: null,
} as unknown as indexersQuery.Indexer;

function _stubMutations(): {
  testMutate: ReturnType<typeof vi.fn>;
  deleteMutate: ReturnType<typeof vi.fn>;
  toggleMutate: ReturnType<typeof vi.fn>;
} {
  const testMutate = vi.fn();
  const deleteMutate = vi.fn();
  const toggleMutate = vi.fn();
  vi.spyOn(indexersQuery, "useTestIndexer").mockReturnValue({
    mutate: testMutate,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof indexersQuery.useTestIndexer>);
  vi.spyOn(indexersQuery, "useDeleteIndexer").mockReturnValue({
    mutate: deleteMutate,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof indexersQuery.useDeleteIndexer>);
  vi.spyOn(indexersQuery, "useToggleIndexer").mockReturnValue({
    mutate: toggleMutate,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof indexersQuery.useToggleIndexer>);
  return { testMutate, deleteMutate, toggleMutate };
}

describe("IndexerRow", () => {
  it("fires useTestIndexer.mutate with the row id when Test is clicked", () => {
    const { testMutate } = _stubMutations();

    renderWithProviders(<IndexerRow indexer={SAMPLE} />, {
      i18nResources: I18N_BUNDLE,
    });

    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(testMutate).toHaveBeenCalledTimes(1);
    expect(testMutate.mock.calls[0]?.[0]).toBe(7);
  });

  it("surfaces the test failure as a role='alert' paragraph", () => {
    _stubMutations();
    vi.spyOn(indexersQuery, "useTestIndexer").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: { message: "401 unauthorized" },
    } as unknown as ReturnType<typeof indexersQuery.useTestIndexer>);

    renderWithProviders(<IndexerRow indexer={SAMPLE} />, {
      i18nResources: I18N_BUNDLE,
    });

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("401 unauthorized");
  });

  it("opens the confirm panel and fires useDeleteIndexer.mutate on Confirm", () => {
    const { deleteMutate } = _stubMutations();

    renderWithProviders(<IndexerRow indexer={SAMPLE} />, {
      i18nResources: I18N_BUNDLE,
    });

    // Initial: confirm panel is hidden.
    expect(screen.queryByText("Delete indexer?")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    // Confirm panel renders.
    expect(screen.getByText("Delete indexer?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(deleteMutate).toHaveBeenCalledTimes(1);
    expect(deleteMutate.mock.calls[0]?.[0]).toBe(7);
  });
});
