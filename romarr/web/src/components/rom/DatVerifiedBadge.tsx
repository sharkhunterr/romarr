/**
 * DAT verification badge (slices 95 + 446).
 *
 * Tri-state badge driven by ``Dump.dat_verified`` + ``Dump.dat_source``:
 *
 *   - ``dat_source == null`` → no entry in any DAT for this hash.
 *     The vast majority of hacks, demos, betas, scans and CHDs
 *     (whose SHA-1 doesn't match the underlying track) fall here.
 *     We return ``null`` so the row stays clean rather than
 *     littered with ``DAT ?``.
 *   - matched + verified → ``DAT ✓`` (emerald).
 *   - matched + un-verified → ``DAT !`` (amber). The match
 *     resolved against a DAT row whose status is BADDUMP/HACK/
 *     OVERDUMP — surface it so the operator can investigate.
 */

import { type ReactElement } from "react";

export interface DatVerifiedBadgeProps {
  /** True when the cascade returned a VERIFIED entry. */
  verified: boolean;
  /** DAT source string (``no-intro`` / ``redump`` / …). ``null`` = no match. */
  source?: string | null;
  className?: string;
}

export function DatVerifiedBadge(
  props: DatVerifiedBadgeProps,
): ReactElement | null {
  const source = props.source ?? null;
  if (source === null) {
    // No DAT entry matched this hash at all — don't paint a "?" on
    // every hack/demo/CHD row.
    return null;
  }

  const colour = props.verified
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-amber-700/30 text-amber-200 ring-amber-500/40";
  const symbol = props.verified ? "✓" : "!";
  const tooltip = props.verified
    ? `Verified against ${source}`
    : `Matched in ${source} but flagged as BADDUMP / HACK / OVERDUMP`;

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
      <span className="text-[0.6rem] uppercase tracking-wider">DAT</span>
      <span aria-hidden="true">{symbol}</span>
    </span>
  );
}
