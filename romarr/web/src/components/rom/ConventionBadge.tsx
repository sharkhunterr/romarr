/**
 * Naming-convention pill.
 *
 * Five documented conventions (No-Intro / Redump / TOSEC /
 * GoodTools / Scene) plus an "unknown" fallback. Colours match
 * the spec 014 design tokens.
 */

import { type ReactElement } from "react";

export type NamingConvention =
  | "no-intro"
  | "redump"
  | "tosec"
  | "goodtools"
  | "scene"
  | "unknown";

export interface ConventionBadgeProps {
  convention: NamingConvention;
  className?: string;
}

const CONVENTION_LABEL: Record<NamingConvention, string> = {
  "no-intro": "No-Intro",
  redump: "Redump",
  tosec: "TOSEC",
  goodtools: "GoodTools",
  scene: "Scene",
  unknown: "Unknown",
};

const CONVENTION_COLORS: Record<NamingConvention, string> = {
  "no-intro": "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  redump: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
  tosec: "bg-zinc-700/30 text-zinc-200 ring-zinc-500/40",
  goodtools: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  scene: "bg-purple-700/30 text-purple-200 ring-purple-500/40",
  unknown: "bg-zinc-800 text-zinc-400 ring-zinc-600",
};

export function ConventionBadge(
  props: ConventionBadgeProps,
): ReactElement {
  const className = [
    "inline-flex items-center rounded-full px-2.5 py-0.5",
    "text-xs font-medium ring-1 ring-inset",
    CONVENTION_COLORS[props.convention],
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span className={className}>
      {CONVENTION_LABEL[props.convention]}
    </span>
  );
}
