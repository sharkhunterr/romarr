/**
 * Pure-CSS shimmer skeletons (T023).
 *
 * Three variants for the three list shapes the operator UI
 * uses: list rows (Library list mode, History), card grid
 * (Library grid mode), and detail (Game tabbed view header).
 *
 * The shimmer animation is a Tailwind ``animate-pulse`` —
 * keeps the runtime cost zero. The Skeleton primitive from
 * shadcn/ui (more polished, gradient-based) lands when shadcn
 * primitives ship.
 */

import { type ReactElement } from "react";

const SHIMMER = "animate-pulse rounded bg-zinc-800";

export interface SkeletonProps {
  className?: string;
}

/** Generic block — use for one-off shimmer rectangles. */
export function Skeleton(props: SkeletonProps): ReactElement {
  const className = [SHIMMER, props.className ?? ""].join(" ").trim();
  return <div className={className} aria-hidden="true" />;
}

/** List row — title + meta line, repeats N times. */
export function ListSkeleton(props: {
  rows?: number;
}): ReactElement {
  const rows = props.rows ?? 6;
  return (
    <ul className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <li
          key={i}
          className="flex items-center gap-3 rounded-md bg-zinc-900/40 p-3"
        >
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-2 w-1/3" />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Card grid — cover + title + meta, repeats N times. */
export function CardGridSkeleton(props: {
  cards?: number;
}): ReactElement {
  const cards = props.cards ?? 8;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {Array.from({ length: cards }, (_, i) => (
        <div
          key={i}
          className="space-y-2 rounded-md bg-zinc-900/40 p-2"
        >
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-2 w-1/2" />
        </div>
      ))}
    </div>
  );
}

/** Detail header — large cover + title + 3 meta rows. */
export function DetailSkeleton(): ReactElement {
  return (
    <div className="flex gap-4">
      <Skeleton className="h-40 w-28 shrink-0" />
      <div className="flex-1 space-y-3 py-1">
        <Skeleton className="h-5 w-3/5" />
        <Skeleton className="h-3 w-2/5" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-1/3" />
      </div>
    </div>
  );
}
