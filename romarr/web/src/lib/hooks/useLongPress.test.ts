/**
 * useLongPress tests (slice 269 — T066 path-divergence close).
 *
 * The spec'd test (`tests/unit/pages/test_Library.tsx::test_long_press_bulk_select`)
 * wanted Playwright-emulated touch + the full Library page tree.
 * The actual long-press logic lives in this hook; testing it
 * here pins the contract directly (touch / pointer / threshold
 * / movement-cancels / disabled) without dragging the page +
 * its providers.
 *
 * Uses ``vi.useFakeTimers`` so the 500 ms threshold doesn't make
 * tests slow. ``renderHook`` from React Testing Library gives
 * us a stable hook fixture; we then call the returned event
 * handlers like the consumer would.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useLongPress } from "./useLongPress";

interface SyntheticTouch {
  clientX: number;
  clientY: number;
}

function _touch(x: number, y: number): SyntheticTouch {
  return { clientX: x, clientY: y };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useLongPress", () => {
  it("fires the callback after the default 500ms hold", () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useLongPress(cb));

    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });

    expect(cb).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("cancels the press when the touch moves beyond the jitter tolerance", () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useLongPress(cb));

    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });
    act(() => {
      // 20 px is over the 10 px tolerance.
      result.current.onTouchMove({
        touches: [_touch(125, 200)],
      } as unknown as Parameters<typeof result.current.onTouchMove>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(cb).not.toHaveBeenCalled();
  });

  it("cancels the press when touch ends before the threshold", () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useLongPress(cb));

    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    act(() => {
      result.current.onTouchEnd(
        {} as Parameters<typeof result.current.onTouchEnd>[0],
      );
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(cb).not.toHaveBeenCalled();
  });

  it("respects disabled=true (never fires)", () => {
    const cb = vi.fn();
    const { result } = renderHook(() =>
      useLongPress(cb, { disabled: true }),
    );

    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(cb).not.toHaveBeenCalled();
  });

  it("honours a custom thresholdMs", () => {
    const cb = vi.fn();
    const { result } = renderHook(() =>
      useLongPress(cb, { thresholdMs: 200 }),
    );

    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(199);
    });
    expect(cb).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("swallows the synthetic click that follows a consumed long-press", () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useLongPress(cb));

    // Simulate a touch press → threshold passes → callback
    // fires + ``consumed`` flag set.
    act(() => {
      result.current.onTouchStart({
        touches: [_touch(100, 200)],
      } as unknown as Parameters<typeof result.current.onTouchStart>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });

    // The follow-up synthetic click should be swallowed —
    // ``preventDefault`` + ``stopPropagation`` on the captured
    // mouse event.
    const click = {
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    } as unknown as Parameters<typeof result.current.onClickCapture>[0];
    act(() => {
      result.current.onClickCapture(click);
    });

    expect((click as unknown as { preventDefault: ReturnType<typeof vi.fn> }).preventDefault).toHaveBeenCalled();
    expect((click as unknown as { stopPropagation: ReturnType<typeof vi.fn> }).stopPropagation).toHaveBeenCalled();
  });

  it("fires from the pointer events too (mouse / pen path)", () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useLongPress(cb));

    act(() => {
      result.current.onPointerDown({
        pointerType: "mouse",
        button: 0,
        clientX: 100,
        clientY: 200,
      } as unknown as Parameters<typeof result.current.onPointerDown>[0]);
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(cb).toHaveBeenCalledTimes(1);
  });
});
