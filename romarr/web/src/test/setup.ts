// Vitest global setup. Loaded once per test process before any
// test file runs.
//
// Wires up:
//   - @testing-library/jest-dom matchers (toBeInTheDocument,
//     toHaveTextContent, etc.) — extends Vitest's built-in
//     `expect` so component tests can read like the canonical
//     Testing Library examples
//   - default cleanup-after-each-test (testing-library/react's
//     auto-cleanup is on by default in vitest with jsdom)
//   - matchMedia + IntersectionObserver shims that jsdom
//     doesn't ship; everything that consumes them in the SPA
//     (ThemeProvider's auto-detect, virtualised lists) wants
//     them at module load time.

import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// matchMedia shim — used by ThemeProvider's prefers-color-scheme
// auto-detect path.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// IntersectionObserver shim — used by react-intersection-observer
// (Library page virtualisation) and the pull-to-refresh hook.
class _IntersectionObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = vi.fn(() => []);
  root: Element | null = null;
  rootMargin = "";
  thresholds: ReadonlyArray<number> = [];
}
Object.defineProperty(window, "IntersectionObserver", {
  writable: true,
  configurable: true,
  value: _IntersectionObserver,
});

// ResizeObserver shim — Radix-UI primitives consume it.
class _ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  configurable: true,
  value: _ResizeObserver,
});

// scrollTo / scrollIntoView shims — Radix scroll-into-view
// behaviour assumes a real browser.
Element.prototype.scrollIntoView = vi.fn();
window.scrollTo = vi.fn() as typeof window.scrollTo;
