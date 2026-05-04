/**
 * useInstallPrompt + install-store tests (spec 014 T051).
 *
 * Pure-store + pure-hook unit tests covering the documented
 * lifecycle:
 *   * Initial state: no event, not installed → canInstall=false.
 *   * After setEvent(deferredEvent): canInstall=true.
 *   * After setInstalled(true): canInstall=false even with an
 *     event present (already-installed shortcut).
 *   * promptInstall() with no event → "unavailable".
 *   * promptInstall() resolves to the user's choice and clears
 *     the deferred event from the store.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useInstallPrompt, useInstallStore } from "./install";

afterEach(() => {
  // Reset store between tests so per-test state doesn't leak.
  useInstallStore.setState({ event: null, isInstalled: false });
});

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function _stubEvent(
  outcome: "accepted" | "dismissed" = "accepted",
): BeforeInstallPromptEvent {
  return {
    type: "beforeinstallprompt",
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome }),
  } as unknown as BeforeInstallPromptEvent;
}

describe("useInstallPrompt", () => {
  it("starts with canInstall=false (no deferred event)", () => {
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isInstalled).toBe(false);
  });

  it("flips canInstall=true after setEvent fires", () => {
    const { result, rerender } = renderHook(() => useInstallPrompt());

    act(() => {
      useInstallStore.getState().setEvent(_stubEvent());
    });
    rerender();

    expect(result.current.canInstall).toBe(true);
    expect(result.current.isInstalled).toBe(false);
  });

  it("canInstall=false when isInstalled is true even with an event", () => {
    const { result, rerender } = renderHook(() => useInstallPrompt());

    act(() => {
      useInstallStore.getState().setEvent(_stubEvent());
      useInstallStore.getState().setInstalled(true);
    });
    rerender();

    expect(result.current.canInstall).toBe(false);
    expect(result.current.isInstalled).toBe(true);
  });

  it("promptInstall() returns 'unavailable' when no event is buffered", async () => {
    const { result } = renderHook(() => useInstallPrompt());

    const outcome = await result.current.promptInstall();
    expect(outcome).toBe("unavailable");
  });

  it("promptInstall() resolves the user's choice and clears the event", async () => {
    const { result, rerender } = renderHook(() => useInstallPrompt());
    const event = _stubEvent("accepted");

    act(() => {
      useInstallStore.getState().setEvent(event);
    });
    rerender();
    expect(result.current.canInstall).toBe(true);

    const outcome = await result.current.promptInstall();
    expect(outcome).toBe("accepted");
    // The browser invalidates the event after the choice resolves;
    // the hook clears it from the store so the UI stops offering
    // the prompt.
    expect(useInstallStore.getState().event).toBeNull();
  });

  it("promptInstall() forwards 'dismissed' choice unchanged", async () => {
    const { result, rerender } = renderHook(() => useInstallPrompt());
    const event = _stubEvent("dismissed");

    act(() => {
      useInstallStore.getState().setEvent(event);
    });
    rerender();

    const outcome = await result.current.promptInstall();
    expect(outcome).toBe("dismissed");
  });
});
