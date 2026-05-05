/**
 * VirtualGrid — responsive virtualized grid (T071).
 *
 * Wraps ``@tanstack/react-virtual``'s row-mode virtualizer
 * around a CSS grid. Computes the number of columns from the
 * viewport width using the same breakpoints the existing
 * Library grid uses (2 / sm:3 / md:4 / lg:6) so the visual
 * rendering stays identical to the non-virtualized grid the
 * page used before.
 *
 * Spec 014 SC-002 + T071 — 60 fps scroll on a 10k-item library.
 * Below ``virtualizeThreshold`` items the component renders the
 * grid normally so small libraries don't pay the
 * absolute-positioning overhead.
 */

import {
  useEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

const _BREAKPOINTS: Array<{ minWidth: number; cols: number }> = [
  { minWidth: 1024, cols: 6 },
  { minWidth: 768, cols: 4 },
  { minWidth: 640, cols: 3 },
  { minWidth: 0, cols: 2 },
];

function _columnsFor(width: number): number {
  for (const bp of _BREAKPOINTS) {
    if (width >= bp.minWidth) return bp.cols;
  }
  return 2;
}

export interface VirtualGridProps<T> {
  items: ReadonlyArray<T>;
  /** Render one item — same shape as the non-virtualized version. */
  renderItem: (item: T, index: number) => ReactNode;
  /** Stable key extractor (avoids index-based remounts on filter). */
  itemKey: (item: T, index: number) => string | number;
  /** Estimated row height in px — covers the tallest expected card. */
  estimatedRowHeight?: number;
  /** Items below this count render unvirtualized for simplicity. */
  virtualizeThreshold?: number;
  /** Extra ARIA label on the scroll container. */
  ariaLabel?: string;
}

export function VirtualGrid<T>(props: VirtualGridProps<T>): ReactElement {
  const {
    items,
    renderItem,
    itemKey,
    estimatedRowHeight = 240,
    virtualizeThreshold = 200,
    ariaLabel,
  } = props;

  const parentRef = useRef<HTMLDivElement | null>(null);
  const [columns, setColumns] = useState<number>(() =>
    typeof window === "undefined" ? 6 : _columnsFor(window.innerWidth),
  );

  useEffect(() => {
    function recompute(): void {
      setColumns(_columnsFor(window.innerWidth));
    }
    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  // ``useVirtualizer`` MUST be called unconditionally per the
  // rules of hooks. We call it on every render with the
  // computed row count; below the threshold the rendered
  // output simply ignores the virtualizer's output.
  const rowCount = Math.ceil(items.length / Math.max(columns, 1));
  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 4,
  });

  // Below the threshold, render a plain CSS grid — the
  // virtualization overhead isn't worth it for small libraries.
  if (items.length < virtualizeThreshold) {
    return (
      <ul
        aria-label={ariaLabel}
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
      >
        {items.map((item, idx) => (
          <li key={itemKey(item, idx)}>{renderItem(item, idx)}</li>
        ))}
      </ul>
    );
  }

  return (
    <div
      ref={parentRef}
      role="list"
      aria-label={ariaLabel}
      className="h-[calc(100vh-220px)] overflow-y-auto"
      // ``contain: strict`` keeps layout work bounded to this node
      // so virtualized scrolling doesn't trigger reflows on the
      // shell.
      style={{ contain: "strict" }}
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const startIdx = virtualRow.index * columns;
          const rowItems = items.slice(startIdx, startIdx + columns);
          return (
            <div
              key={virtualRow.key}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
              className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
            >
              {rowItems.map((item, colIdx) => {
                const idx = startIdx + colIdx;
                return (
                  <div
                    key={itemKey(item, idx)}
                    role="listitem"
                  >
                    {renderItem(item, idx)}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
