/**
 * sw-update tests (CL012).
 *
 * Pure-store tests covering the documented lifecycle:
 *   * initial state: needsRefresh=false, triggerUpdate=null;
 *   * setNeedsRefresh fills both fields;
 *   * dismissUpdate clears them;
 *   * applyUpdate calls the trigger then reloads the page.
 *
 * The ``virtual:pwa-register`` import is dynamic + try/catch'd
 * inside ``registerServiceWorker``; we don't exercise the
 * registration path in jsdom — the contract above is what the
 * toast actually subscribes to.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyUpdate,
  dismissUpdate,
  useSwUpdateStore,
} from "./index";

const _origLocation = window.location;

beforeEach(() => {
  // jsdom freezes window.location.reload, so we swap the whole
  // location object for a writable stub during the test.
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { ..._origLocation, reload: vi.fn() },
  });
});

afterEach(() => {
  useSwUpdateStore.setState({ needsRefresh: false, triggerUpdate: null });
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: _origLocation,
  });
  vi.restoreAllMocks();
});

describe("useSwUpdateStore", () => {
  it("starts with needsRefresh=false and no trigger", () => {
    const state = useSwUpdateStore.getState();
    expect(state.needsRefresh).toBe(false);
    expect(state.triggerUpdate).toBeNull();
  });

  it("setNeedsRefresh fills the flag and the trigger", () => {
    const trigger = vi.fn().mockResolvedValue(undefined);
    useSwUpdateStore.getState().setNeedsRefresh(true, trigger);

    const state = useSwUpdateStore.getState();
    expect(state.needsRefresh).toBe(true);
    expect(state.triggerUpdate).toBe(trigger);
  });

  it("dismissUpdate clears the flag and trigger (existing SW stays)", () => {
    const trigger = vi.fn().mockResolvedValue(undefined);
    useSwUpdateStore.getState().setNeedsRefresh(true, trigger);

    dismissUpdate();

    const state = useSwUpdateStore.getState();
    expect(state.needsRefresh).toBe(false);
    expect(state.triggerUpdate).toBeNull();
    expect(trigger).not.toHaveBeenCalled();
  });

  it("applyUpdate calls the trigger then reloads the page", async () => {
    const trigger = vi.fn().mockResolvedValue(undefined);
    useSwUpdateStore.getState().setNeedsRefresh(true, trigger);

    await applyUpdate();

    expect(trigger).toHaveBeenCalledTimes(1);
    expect(window.location.reload).toHaveBeenCalledTimes(1);
  });

  it("applyUpdate is a no-op when no trigger is buffered", async () => {
    await applyUpdate();

    expect(window.location.reload).not.toHaveBeenCalled();
  });
});
