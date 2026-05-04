/**
 * useSearchStore test (spec 014 T112).
 *
 * Pure store unit tests for the recent-searches plumbing:
 *
 *   * pushRecent dedupes on case-insensitive match (a repeated
 *     query bubbles to the top instead of duplicating).
 *   * pushRecent caps at 5 entries (the documented max).
 *   * pushRecent ignores empty / whitespace-only queries.
 *   * clearRecent empties the list.
 */

import { afterEach, describe, expect, it } from "vitest";

import { useSearchStore } from "./search";

afterEach(() => {
  // Reset the store so tests don't leak state into each other.
  useSearchStore.getState().clearRecent();
  useSearchStore.getState().closeModal();
});

describe("useSearchStore", () => {
  it("starts with an empty recent list and closed modal", () => {
    const state = useSearchStore.getState();
    expect(state.recent).toEqual([]);
    expect(state.open).toBe(false);
  });

  it("pushRecent prepends new queries and dedupes case-insensitively", () => {
    const { pushRecent } = useSearchStore.getState();
    pushRecent("Sonic");
    pushRecent("Mario");
    // Same query in different casing → bubbles to the top.
    pushRecent("sonic");

    expect(useSearchStore.getState().recent).toEqual(["sonic", "Mario"]);
  });

  it("pushRecent caps the list at 5 entries (oldest dropped)", () => {
    const { pushRecent } = useSearchStore.getState();
    for (const q of ["a", "b", "c", "d", "e", "f", "g"]) {
      pushRecent(q);
    }
    const recent = useSearchStore.getState().recent;
    expect(recent).toHaveLength(5);
    // Most-recent first.
    expect(recent[0]).toBe("g");
    // Oldest two ("a", "b") are dropped.
    expect(recent).not.toContain("a");
    expect(recent).not.toContain("b");
  });

  it("pushRecent ignores empty / whitespace-only queries", () => {
    const { pushRecent } = useSearchStore.getState();
    pushRecent("");
    pushRecent("   ");
    pushRecent("\t\n");
    expect(useSearchStore.getState().recent).toEqual([]);
  });

  it("clearRecent empties the list", () => {
    const { pushRecent, clearRecent } = useSearchStore.getState();
    pushRecent("Sonic");
    pushRecent("Mario");
    clearRecent();
    expect(useSearchStore.getState().recent).toEqual([]);
  });

  it("openModal / closeModal / toggleModal flip the open flag", () => {
    const { openModal, closeModal, toggleModal } = useSearchStore.getState();

    openModal();
    expect(useSearchStore.getState().open).toBe(true);

    closeModal();
    expect(useSearchStore.getState().open).toBe(false);

    toggleModal();
    expect(useSearchStore.getState().open).toBe(true);
    toggleModal();
    expect(useSearchStore.getState().open).toBe(false);
  });
});
