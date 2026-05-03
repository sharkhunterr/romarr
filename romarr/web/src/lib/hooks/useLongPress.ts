/**
 * Long-press detection hook for mobile multi-select (slice 158).
 *
 * Returns a set of event handlers to spread onto an element.
 * Triggers the supplied callback when the user holds touch /
 * primary mouse for ``thresholdMs`` (default 500). Movement
 * beyond a small jitter cancels the press so an in-progress
 * scroll never accidentally activates selection.
 *
 * The follow-up click is swallowed by setting an internal
 * "consumed" flag and calling ``event.preventDefault`` on the
 * synthetic click via ``onClickCapture`` — this matters for
 * ``<Link>`` and ``<button>`` elements that would otherwise
 * navigate or fire their click handler immediately after the
 * touch ends.
 */

import {
  useCallback,
  useRef,
  type MouseEvent,
  type PointerEvent,
  type TouchEvent,
} from "react";

const DEFAULT_THRESHOLD_MS = 500;
const MOVE_TOLERANCE_PX = 10;

export interface LongPressHandlers {
  onTouchStart: (e: TouchEvent) => void;
  onTouchMove: (e: TouchEvent) => void;
  onTouchEnd: (e: TouchEvent) => void;
  onTouchCancel: (e: TouchEvent) => void;
  onPointerDown: (e: PointerEvent) => void;
  onPointerMove: (e: PointerEvent) => void;
  onPointerUp: (e: PointerEvent) => void;
  onPointerCancel: (e: PointerEvent) => void;
  onPointerLeave: (e: PointerEvent) => void;
  onContextMenu: (e: MouseEvent) => void;
  onClickCapture: (e: MouseEvent) => void;
}

interface Options {
  /** Hold duration to trigger long-press, in ms. */
  thresholdMs?: number;
  /**
   * If true, the hook does nothing — useful when the consumer
   * wants to disable long-press in some states (e.g., already
   * in selection mode).
   */
  disabled?: boolean;
}

interface PressState {
  timer: number | null;
  startX: number;
  startY: number;
  consumed: boolean;
}

export function useLongPress(
  onLongPress: () => void,
  options: Options = {},
): LongPressHandlers {
  const { thresholdMs = DEFAULT_THRESHOLD_MS, disabled = false } = options;
  const stateRef = useRef<PressState>({
    timer: null,
    startX: 0,
    startY: 0,
    consumed: false,
  });

  const cancel = useCallback(() => {
    if (stateRef.current.timer !== null) {
      window.clearTimeout(stateRef.current.timer);
      stateRef.current.timer = null;
    }
  }, []);

  const start = useCallback(
    (x: number, y: number) => {
      if (disabled) return;
      cancel();
      stateRef.current.startX = x;
      stateRef.current.startY = y;
      stateRef.current.consumed = false;
      stateRef.current.timer = window.setTimeout(() => {
        stateRef.current.consumed = true;
        onLongPress();
      }, thresholdMs);
    },
    [cancel, disabled, onLongPress, thresholdMs],
  );

  const moved = useCallback((x: number, y: number) => {
    const dx = Math.abs(x - stateRef.current.startX);
    const dy = Math.abs(y - stateRef.current.startY);
    if (dx > MOVE_TOLERANCE_PX || dy > MOVE_TOLERANCE_PX) {
      if (stateRef.current.timer !== null) {
        window.clearTimeout(stateRef.current.timer);
        stateRef.current.timer = null;
      }
    }
  }, []);

  return {
    onTouchStart: (e) => {
      const touch = e.touches[0];
      if (touch !== undefined) start(touch.clientX, touch.clientY);
    },
    onTouchMove: (e) => {
      const touch = e.touches[0];
      if (touch !== undefined) moved(touch.clientX, touch.clientY);
    },
    onTouchEnd: () => cancel(),
    onTouchCancel: () => cancel(),
    onPointerDown: (e) => {
      // Only react to primary pointer (touch / left-click).
      if (e.pointerType === "mouse" && e.button !== 0) return;
      start(e.clientX, e.clientY);
    },
    onPointerMove: (e) => moved(e.clientX, e.clientY),
    onPointerUp: () => cancel(),
    onPointerCancel: () => cancel(),
    onPointerLeave: () => cancel(),
    onContextMenu: (e) => {
      // Mobile browsers sometimes trigger contextmenu on
      // long-press; consume it so the OS menu doesn't compete
      // with our selection UI. If the press triggered the
      // long-press already, we've also captured the synthetic
      // click — preventDefault here is the belt-and-suspenders.
      if (stateRef.current.consumed || stateRef.current.timer !== null) {
        e.preventDefault();
      }
    },
    onClickCapture: (e) => {
      // After a long-press fires, the touchend produces a
      // synthetic click that would otherwise navigate the
      // wrapping <Link>. Swallow it.
      if (stateRef.current.consumed) {
        e.preventDefault();
        e.stopPropagation();
        stateRef.current.consumed = false;
      }
    },
  };
}
