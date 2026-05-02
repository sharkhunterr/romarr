/**
 * Small text-based platform icon — manufacturer initial in a
 * coloured circle.
 *
 * The full SVG-sprite implementation (T035 in the spec) lands
 * with the Platform Pack assets slice, when icons get bundled
 * with the spec 003 platform metadata. Today's component is a
 * cheap, dependency-free stand-in that gives every platform a
 * consistent visual cue without shipping ~50 SVG files
 * preemptively.
 */

import { type ReactElement } from "react";

export interface PlatformIconProps {
  /** Kebab-case slug, e.g. ``mega-drive``, ``snes``. */
  slug: string;
  /** Display name; used as a tooltip + a11y label. */
  name?: string;
  /** Manufacturer hint used to colour the badge. */
  manufacturer?: string;
  className?: string;
}

const MANUFACTURER_COLORS: Record<string, string> = {
  sega: "bg-blue-600 text-white",
  nintendo: "bg-red-600 text-white",
  sony: "bg-zinc-700 text-zinc-100",
  microsoft: "bg-emerald-600 text-white",
  atari: "bg-amber-700 text-amber-50",
  snk: "bg-orange-600 text-white",
  nec: "bg-indigo-600 text-white",
  bandai: "bg-purple-600 text-white",
};

const SLUG_COLORS: Record<string, string> = {
  megadrive: "bg-blue-700 text-white",
  "mega-drive": "bg-blue-700 text-white",
  snes: "bg-purple-700 text-white",
  nes: "bg-red-700 text-white",
  gba: "bg-violet-600 text-white",
  gameboy: "bg-emerald-700 text-white",
  "game-boy": "bg-emerald-700 text-white",
  ps1: "bg-zinc-700 text-zinc-100",
  ps2: "bg-zinc-800 text-zinc-100",
};

const NEUTRAL = "bg-zinc-800 text-zinc-200";

function pickClass(props: PlatformIconProps): string {
  const slugKey = props.slug.toLowerCase();
  if (SLUG_COLORS[slugKey]) {
    return SLUG_COLORS[slugKey];
  }
  if (props.manufacturer) {
    const mfr = props.manufacturer.toLowerCase();
    if (MANUFACTURER_COLORS[mfr]) {
      return MANUFACTURER_COLORS[mfr];
    }
  }
  return NEUTRAL;
}

export function PlatformIcon(
  props: PlatformIconProps,
): ReactElement {
  const initial = props.slug.slice(0, 2).toUpperCase();
  const className = [
    "inline-flex h-6 w-6 items-center justify-center rounded",
    "text-[0.65rem] font-mono font-bold",
    pickClass(props),
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span
      className={className}
      title={props.name ?? props.slug}
      aria-label={props.name ?? `Platform ${props.slug}`}
    >
      {initial}
    </span>
  );
}
