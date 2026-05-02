/**
 * Global-search store (T110-T113).
 *
 * Two slots:
 *   * `open`  — modal visibility, toggled by the ⌘+K hotkey
 *               or the BottomNav search button.
 *   * `recent` — last five operator queries, persisted in
 *                localStorage under `romarr.search.recent`.
 *
 * The recent list is intentionally NOT a full LRU stack — we
 * dedupe on push so a repeated query bubbles to the top.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const RECENT_KEY = "romarr.search.recent";
const RECENT_MAX = 5;

interface SearchState {
  open: boolean;
  recent: string[];
  openModal: () => void;
  closeModal: () => void;
  toggleModal: () => void;
  pushRecent: (query: string) => void;
  clearRecent: () => void;
}

export const useSearchStore = create<SearchState>()(
  persist(
    (set, get) => ({
      open: false,
      recent: [],
      openModal: () => set({ open: true }),
      closeModal: () => set({ open: false }),
      toggleModal: () => set({ open: !get().open }),
      pushRecent: (query) => {
        const trimmed = query.trim();
        if (trimmed.length === 0) return;
        const filtered = get().recent.filter(
          (q) => q.toLowerCase() !== trimmed.toLowerCase(),
        );
        set({ recent: [trimmed, ...filtered].slice(0, RECENT_MAX) });
      },
      clearRecent: () => set({ recent: [] }),
    }),
    {
      name: RECENT_KEY,
      partialize: (state) => ({ recent: state.recent }),
    },
  ),
);
