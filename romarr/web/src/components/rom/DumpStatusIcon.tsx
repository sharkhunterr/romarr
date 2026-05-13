/**
 * Dump-quality icon + colour.
 *
 * Status enum mirrors :class:`romarr.domain.enums.DumpStatus`:
 * verified ✓, hack ⚠, proto 🚧, trainer 🔧, baddump ❌,
 * overdump 📛 — plus ``good``, ``beta``, ``demo``, ``sample``,
 * ``translation``, ``unknown`` for completeness. Each maps to a
 * semantic colour cue used across the Library / Game Detail UI.
 */

import { type ReactElement } from "react";

export type DumpStatus =
  | "verified"
  | "good"
  | "proto"
  | "beta"
  | "demo"
  | "sample"
  | "hack"
  | "trainer"
  | "translation"
  | "baddump"
  | "overdump"
  | "unknown";

export interface DumpStatusIconProps {
  status: DumpStatus;
  className?: string;
  /** Hide the textual label (icon-only) — used in dense lists. */
  iconOnly?: boolean;
  /** Hide the emoji glyph — surfaces the textual label only.
   * Wins over ``iconOnly`` when both are set. */
  noEmoji?: boolean;
}

const STATUS_ICON: Record<DumpStatus, string> = {
  verified: "✓",
  good: "✓",
  proto: "🚧",
  beta: "🚧",
  demo: "🎮",
  sample: "🎮",
  hack: "⚠",
  trainer: "🔧",
  translation: "🌐",
  baddump: "❌",
  overdump: "📛",
  unknown: "❓",
};

const STATUS_LABEL: Record<DumpStatus, string> = {
  verified: "Verified",
  good: "Good",
  proto: "Prototype",
  beta: "Beta",
  demo: "Demo",
  sample: "Sample",
  hack: "Hack",
  trainer: "Trainer",
  translation: "Translation",
  baddump: "Bad dump",
  overdump: "Overdump",
  unknown: "Unknown",
};

const STATUS_COLORS: Record<DumpStatus, string> = {
  verified: "text-emerald-400",
  good: "text-emerald-400",
  proto: "text-sky-400",
  beta: "text-sky-400",
  demo: "text-zinc-300",
  sample: "text-zinc-300",
  hack: "text-amber-400",
  trainer: "text-yellow-400",
  translation: "text-blue-400",
  baddump: "text-red-400",
  overdump: "text-red-400",
  unknown: "text-zinc-500",
};

export function DumpStatusIcon(
  props: DumpStatusIconProps,
): ReactElement {
  const className = [
    "inline-flex items-center gap-1 text-xs font-medium",
    STATUS_COLORS[props.status],
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  if (props.noEmoji) {
    return (
      <span
        className={[
          "inline-flex items-center rounded-md bg-zinc-800 px-1.5 py-0.5",
          "text-[0.6rem] font-mono uppercase tracking-wider ring-1 ring-inset ring-zinc-700",
          STATUS_COLORS[props.status],
          props.className ?? "",
        ]
          .join(" ")
          .trim()}
        title={STATUS_LABEL[props.status]}
        aria-label={STATUS_LABEL[props.status]}
      >
        {STATUS_LABEL[props.status]}
      </span>
    );
  }
  return (
    <span
      className={className}
      title={STATUS_LABEL[props.status]}
      aria-label={STATUS_LABEL[props.status]}
    >
      <span aria-hidden="true">{STATUS_ICON[props.status]}</span>
      {!props.iconOnly && <span>{STATUS_LABEL[props.status]}</span>}
    </span>
  );
}
