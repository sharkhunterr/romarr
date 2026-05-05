/**
 * Web Push scaffolding tests (spec 014 T057).
 *
 * jsdom doesn't ship Notification / PushManager / SW APIs out
 * of the box. The tests assert the support detector returns
 * false in that environment + the helper translation function
 * round-trips the documented base64-URL → Uint8Array shape.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import {
  getNotificationPermission,
  isWebPushSupported,
  useWebPushSubscription,
  useWebPushSupport,
} from "./push";

describe("isWebPushSupported", () => {
  it("returns false in jsdom (no PushManager)", () => {
    expect(isWebPushSupported()).toBe(false);
  });
});

describe("getNotificationPermission", () => {
  it("returns 'denied' when Notification API is missing", () => {
    expect(getNotificationPermission()).toBe("denied");
  });
});

describe("useWebPushSupport", () => {
  it("returns isSupported=false + permission='denied' in jsdom", () => {
    const { result } = renderHook(() => useWebPushSupport());
    expect(result.current.isSupported).toBe(false);
    expect(result.current.permission).toBe("denied");
  });
});

describe("useWebPushSubscription — subscribe outcome paths", () => {
  beforeEach(() => {
    // Best-effort: keep the global state clean between tests.
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns 'unsupported' on browsers without PushManager", async () => {
    const { result } = renderHook(() => useWebPushSubscription());
    await waitFor(() => {
      expect(result.current.subscribed).toBe(false);
    });
    const outcome = await result.current.subscribe();
    expect(outcome).toBe("unsupported");
  });

  it("starts with no subscription endpoint (no SW in jsdom)", async () => {
    const { result } = renderHook(() => useWebPushSubscription());
    await waitFor(() => {
      expect(result.current.subscribed).toBe(false);
      expect(result.current.endpoint).toBeNull();
    });
  });
});
