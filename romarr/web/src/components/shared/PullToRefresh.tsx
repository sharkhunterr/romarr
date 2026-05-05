/**
 * Pull-to-refresh wrapper for list views (spec 014 T018 / T026).
 *
 * Native iOS/Android browsers and the operator's PWA shell trigger
 * the gesture via vertical drag from the top of a scroll container.
 * The component:
 *
 *   * captures vertical drag events via ``@use-gesture/react``;
 *   * shows a translateY indicator that follows the finger up to a
 *     threshold (``triggerDistance``);
 *   * fires ``onRefresh`` on release if the threshold was crossed
 *     (with a Promise-aware "refreshing" state that disables the
 *     pull while the async work runs).
 *
 * Only fires when the wrapped scroll container is at the top
 * (``scrollTop === 0``) so the gesture doesn't fight a normal
 * scroll-up. Touch-action ``pan-y`` keeps native scrolling
 * available below the threshold.
 *
 * The component is intentionally framework-agnostic about the
 * refresh source: callers wire it to a TanStack Query
 * ``query.refetch()`` or a custom imperative reload.
 */

import { useRef, useState, type ReactElement, type ReactNode } from "react";
import { useDrag } from "@use-gesture/react";
import { useTranslation } from "react-i18next";

interface PullToRefreshProps {
  /** Awaitable refresh callback. UI shows the indicator until it resolves. */
  onRefresh: () => Promise<void> | void;
  /** Drag distance (px) to cross before release fires onRefresh. Default 64. */
  triggerDistance?: number;
  /** Maximum drag distance the indicator follows before clamping. Default 120. */
  maxDistance?: number;
  /** Disable the gesture entirely (e.g., when offline / mid-mutation). */
  disabled?: boolean;
  /** The scrollable list/grid being refreshed. */
  children: ReactNode;
  /**
   * Optional className passed to the root wrapper. The drop-in
   * usage on a page is to wrap the list directly without extra
   * styling — this prop is for callers that need the wrapper
   * to participate in flex/grid layouts.
   */
  className?: string;
}

/** Internal state machine: idle → pulling → triggered → refreshing → idle. */
type State = "idle" | "pulling" | "triggered" | "refreshing";

export function PullToRefresh(props: PullToRefreshProps): ReactElement {
  const {
    onRefresh,
    triggerDistance = 64,
    maxDistance = 120,
    disabled = false,
    children,
    className,
  } = props;

  const { t } = useTranslation("common");
  const [state, setState] = useState<State>("idle");
  const [offset, setOffset] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const bind = useDrag(
    ({ down, movement: [, my], cancel, last }) => {
      if (disabled || state === "refreshing") {
        return;
      }
      // Only allow the gesture when the wrapped container is at the top.
      const scrollTop = containerRef.current?.scrollTop ?? 0;
      if (scrollTop > 0 && my > 0) {
        cancel();
        return;
      }

      const clamped = Math.min(Math.max(my, 0), maxDistance);
      if (down) {
        setOffset(clamped);
        setState(clamped >= triggerDistance ? "triggered" : "pulling");
        return;
      }
      if (last) {
        if (clamped >= triggerDistance) {
          setState("refreshing");
          setOffset(triggerDistance);
          Promise.resolve(onRefresh()).finally(() => {
            setOffset(0);
            setState("idle");
          });
        } else {
          setOffset(0);
          setState("idle");
        }
      }
    },
    {
      axis: "y",
      filterTaps: true,
      pointer: { touch: true },
    },
  );

  const indicatorLabel =
    state === "refreshing"
      ? t("pullToRefresh.refreshing", "Refreshing…")
      : state === "triggered"
        ? t("pullToRefresh.release", "Release to refresh")
        : t("pullToRefresh.pull", "Pull to refresh");

  return (
    <div
      {...bind()}
      className={[
        "relative overflow-hidden",
        "touch-pan-y",
        className ?? "",
      ].join(" ")}
      data-state={state}
    >
      <div
        aria-live="polite"
        className={[
          "absolute left-0 right-0 top-0 flex h-12 items-center justify-center",
          "text-xs text-zinc-400",
          "pointer-events-none",
        ].join(" ")}
        style={{
          transform: `translateY(${offset - 48}px)`,
          opacity: state === "idle" ? 0 : 1,
          transition:
            state === "refreshing" || state === "idle"
              ? "transform 200ms ease, opacity 200ms ease"
              : "none",
        }}
      >
        {indicatorLabel}
      </div>
      <div
        ref={containerRef}
        className="h-full overflow-auto"
        style={{
          transform: `translateY(${offset}px)`,
          transition:
            state === "refreshing" || state === "idle"
              ? "transform 200ms ease"
              : "none",
        }}
      >
        {children}
      </div>
    </div>
  );
}
