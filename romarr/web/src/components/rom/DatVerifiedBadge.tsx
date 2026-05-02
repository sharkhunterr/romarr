/**
 * "DAT ✓" / "DAT ?" badge.
 *
 * Indicates whether a Release / Dump matches a known DAT entry
 * (No-Intro, Redump, TOSEC). The tooltip carries the source DAT
 * name when verified; the empty state surfaces a link to the
 * DAT-sources settings page (wired in the Game Detail page
 * slice).
 */

import { type ReactElement } from "react";

export interface DatVerifiedBadgeProps {
  /** True when the dump's hash matches a DAT entry. */
  verified: boolean;
  /** DAT source name (e.g. "No-Intro 2026-04") when verified. */
  source?: string;
  className?: string;
}

export function DatVerifiedBadge(
  props: DatVerifiedBadgeProps,
): ReactElement {
  const colour = props.verified
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-zinc-800 text-zinc-400 ring-zinc-600";
  const symbol = props.verified ? "✓" : "?";
  const tooltip = props.verified
    ? props.source
      ? `Verified against ${props.source}`
      : "Verified"
    : "No DAT match — open DAT sources settings to refresh";

  const className = [
    "inline-flex items-center gap-1 rounded-md px-2 py-0.5",
    "text-xs font-mono font-medium ring-1 ring-inset",
    colour,
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span className={className} title={tooltip}>
      <span className="text-[0.6rem] uppercase tracking-wider">
        DAT
      </span>
      <span aria-hidden="true">{symbol}</span>
    </span>
  );
}
