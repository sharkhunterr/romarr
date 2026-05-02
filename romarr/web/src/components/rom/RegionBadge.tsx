/**
 * Flag emoji + ISO code badge with semantic colour per region.
 *
 * Regions follow the standard No-Intro / Redump set; unknown
 * codes fall through to a neutral grey badge.
 */

import { type CSSProperties, type ReactElement } from "react";

export interface RegionBadgeProps {
  code: string;
  className?: string;
}

const REGION_FLAGS: Record<string, string> = {
  USA: "🇺🇸",
  EUR: "🇪🇺",
  JPN: "🇯🇵",
  AUS: "🇦🇺",
  KOR: "🇰🇷",
  CHN: "🇨🇳",
  BRA: "🇧🇷",
  ESP: "🇪🇸",
  ITA: "🇮🇹",
  FRA: "🇫🇷",
  GER: "🇩🇪",
  RUS: "🇷🇺",
  WLD: "🌐",
  UNK: "❓",
};

const REGION_COLORS: Record<string, string> = {
  USA: "bg-blue-700/30 text-blue-200 ring-blue-500/40",
  EUR: "bg-yellow-700/30 text-yellow-100 ring-yellow-500/40",
  JPN: "bg-red-700/30 text-red-100 ring-red-500/40",
  WLD: "bg-zinc-700/30 text-zinc-100 ring-zinc-500/40",
};

const NEUTRAL_CLASS =
  "bg-zinc-800 text-zinc-200 ring-zinc-600";

const _styleSentinel: CSSProperties = {};
void _styleSentinel;

export function RegionBadge(props: RegionBadgeProps): ReactElement {
  const code = props.code.toUpperCase();
  const flag = REGION_FLAGS[code] ?? "🏳️";
  const colour = REGION_COLORS[code] ?? NEUTRAL_CLASS;
  const className = [
    "inline-flex items-center gap-1 rounded-md px-2 py-0.5",
    "text-xs font-mono font-medium ring-1 ring-inset",
    colour,
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span className={className} aria-label={`Region ${code}`}>
      <span aria-hidden="true">{flag}</span>
      <span>{code}</span>
    </span>
  );
}
