/**
 * Reusable stat card. Used by the Dashboard for system info,
 * total counts, etc.
 */

import { type ReactElement, type ReactNode } from "react";

import { Skeleton } from "@/components/shared/LoadingSkeleton";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  /** True while the underlying query is in flight. */
  loading?: boolean;
  /** Footer text — typically a unit or qualifier ("seconds", "today"). */
  hint?: ReactNode;
  className?: string;
}

export function StatCard(props: StatCardProps): ReactElement {
  const className = [
    "rounded-lg border border-zinc-800 bg-zinc-900/60",
    "px-4 py-3",
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <div className={className}>
      <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
        {props.label}
      </p>
      <div className="mt-1.5 font-mono text-xl font-semibold text-zinc-100">
        {props.loading ? (
          <Skeleton className="h-5 w-20" />
        ) : (
          props.value
        )}
      </div>
      {props.hint && (
        <p className="mt-1 text-[0.7rem] text-zinc-500">{props.hint}</p>
      )}
    </div>
  );
}
