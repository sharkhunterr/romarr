/**
 * DAT verification badge (slices 95 / 446 / 450).
 *
 * Pure-icon variant. Four states, each surfaced by a lucide
 * glyph rather than a "DAT" text label:
 *
 *   - ``status="verified"`` → emerald ``ShieldCheck`` — the
 *     dump's hash matched a known-good (VERIFIED) DAT entry.
 *   - ``status="invalid"`` → amber ``ShieldAlert`` — matched
 *     an entry the DAT flags as BADDUMP / HACK / OVERDUMP.
 *   - ``status="unknown"`` → zinc ``ShieldQuestion`` — we
 *     *had* a hash to check (so it isn't a CHD / hack / PDF)
 *     but the loaded DAT cache had no row for it. Useful in
 *     the search modal to distinguish "we tried" from "we
 *     couldn't try".
 *   - ``status="absent"`` (or omitted) → render ``null`` so
 *     the row stays clean.
 */

import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { type ReactElement } from "react";

export type DatVerifiedStatus = "verified" | "invalid" | "unknown" | "absent";

export interface DatVerifiedBadgeProps {
  status: DatVerifiedStatus;
  /** Optional tooltip override. */
  title?: string;
  className?: string;
}

const _CONFIG: Record<
  Exclude<DatVerifiedStatus, "absent">,
  { Icon: typeof ShieldCheck; chip: string; defaultTitle: string }
> = {
  verified: {
    Icon: ShieldCheck,
    chip:
      "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
    defaultTitle:
      "Hash verified against a DAT database (No-Intro / Redump / …)",
  },
  invalid: {
    Icon: ShieldAlert,
    chip: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
    defaultTitle:
      "Hash matched a DAT row flagged as BADDUMP / HACK / OVERDUMP",
  },
  unknown: {
    Icon: ShieldQuestion,
    chip: "bg-zinc-700/40 text-zinc-300 ring-zinc-500/40",
    defaultTitle:
      "Hash was available but not found in the loaded DAT cache",
  },
};

export function DatVerifiedBadge(
  props: DatVerifiedBadgeProps,
): ReactElement | null {
  if (props.status === "absent") return null;
  const cfg = _CONFIG[props.status];
  const className = [
    "inline-flex items-center justify-center",
    "rounded-md p-1 ring-1 ring-inset",
    cfg.chip,
    props.className ?? "",
  ]
    .join(" ")
    .trim();
  return (
    <span className={className} title={props.title ?? cfg.defaultTitle}>
      <cfg.Icon size={12} strokeWidth={2.5} aria-hidden="true" />
    </span>
  );
}
