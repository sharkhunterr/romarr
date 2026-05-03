/**
 * Single-release row used by both Wanted tabs.
 *
 * Composes the slice 43 ROM components: ConventionBadge,
 * DumpStatusIcon, RegionBadge, LanguagePills. The row is a
 * Link that routes to the future GameDetail page (P-GAME) so
 * the operator can drill in to the full release surface.
 */

import { type ReactElement } from "react";
import { Link } from "react-router-dom";

import {
  ConventionBadge,
  DumpStatusIcon,
  LanguagePills,
  RegionBadge,
  type DumpStatus,
  type NamingConvention,
} from "@/components/rom";
import type { WantedRelease } from "@/lib/api/queries/wanted";

export interface ReleaseRowProps {
  release: WantedRelease;
}

const KNOWN_CONVENTIONS: ReadonlySet<NamingConvention> = new Set([
  "no-intro",
  "redump",
  "tosec",
  "goodtools",
  "scene",
  "unknown",
]);

const KNOWN_DUMP_STATUSES: ReadonlySet<DumpStatus> = new Set([
  "verified",
  "good",
  "proto",
  "beta",
  "demo",
  "sample",
  "hack",
  "trainer",
  "translation",
  "baddump",
  "overdump",
  "unknown",
]);

function asConvention(raw: string): NamingConvention {
  return KNOWN_CONVENTIONS.has(raw as NamingConvention)
    ? (raw as NamingConvention)
    : "unknown";
}

function asDumpStatus(raw: string): DumpStatus {
  return KNOWN_DUMP_STATUSES.has(raw as DumpStatus)
    ? (raw as DumpStatus)
    : "unknown";
}

export function ReleaseRow(props: ReleaseRowProps): ReactElement {
  const { release } = props;
  return (
    <Link
      to={`/game/${release.gameId}`}
      className={[
        "flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
        "hover:border-brand/40 hover:bg-zinc-900",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
        "transition-colors",
      ].join(" ")}
    >
      <p className="truncate text-sm font-medium text-zinc-100">
        {release.name}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {release.regions.map((code) => (
          <RegionBadge key={`${release.id}-${code}`} code={code} />
        ))}
        <ConventionBadge
          convention={asConvention(release.namingConvention)}
        />
        <DumpStatusIcon
          status={asDumpStatus(release.dumpStatus)}
          iconOnly
        />
        {release.languages.length > 0 && (
          <LanguagePills codes={release.languages} max={3} />
        )}
        {release.discTotal > 1 && (
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
            Disc {release.discNumber}/{release.discTotal}
          </span>
        )}
        {release.revision && (
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
            rev {release.revision}
          </span>
        )}
      </div>
    </Link>
  );
}
