/**
 * Numeric Custom-Format score with optional breakdown tooltip.
 *
 * The breakdown surface (per-CustomFormat contributions visible
 * on hover) wires through the shadcn/ui Tooltip primitive in a
 * follow-up slice; today the title attribute carries the
 * breakdown verbatim, which is enough for the spec test (T032)
 * and for accessibility.
 */

import { type ReactElement } from "react";

export interface ScoreBreakdownEntry {
  format: string;
  contribution: number;
}

export interface ScoreBadgeProps {
  score: number;
  breakdown?: readonly ScoreBreakdownEntry[];
  className?: string;
}

function formatBreakdown(
  breakdown: readonly ScoreBreakdownEntry[] | undefined,
): string | undefined {
  if (!breakdown || breakdown.length === 0) {
    return undefined;
  }
  return breakdown
    .map(
      (entry) =>
        `${entry.format}: ${entry.contribution >= 0 ? "+" : ""}${entry.contribution}`,
    )
    .join("\n");
}

export function ScoreBadge(props: ScoreBadgeProps): ReactElement {
  const positive = props.score >= 0;
  const colour = positive
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-red-700/30 text-red-200 ring-red-500/40";

  const className = [
    "inline-flex items-center rounded-md px-2 py-0.5",
    "text-xs font-mono font-medium ring-1 ring-inset",
    colour,
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span className={className} title={formatBreakdown(props.breakdown)}>
      {positive ? "+" : ""}
      {props.score}
    </span>
  );
}
