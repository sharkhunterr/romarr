/**
 * Single-release row used by both Wanted tabs
 * (slices 68, 152, 158).
 *
 * Composes the slice 43 ROM components: ConventionBadge,
 * DumpStatusIcon, RegionBadge, LanguagePills. The row is a
 * Link that routes to GameDetail so the operator can drill in
 * to the full release surface.
 *
 * In bulk-select mode the row swaps to a button that toggles
 * inclusion in the selection set; a brand-tinted ring + ✓
 * marker show selected state.
 *
 * On mobile, holding a row for ~500 ms (long-press) fires
 * ``onLongPress`` so the parent can flip into selection mode
 * pre-selecting the held row — matches spec D.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  ConventionBadge,
  DumpStatusIcon,
  LanguagePills,
  RegionBadge,
  type DumpStatus,
  type NamingConvention,
} from "@/components/rom";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import type { WantedRelease } from "@/lib/api/queries/wanted";
import { useLongPress } from "@/lib/hooks/useLongPress";

export interface ReleaseRowProps {
  release: WantedRelease;
  selectionActive?: boolean;
  selected?: boolean;
  onToggleSelect?: (releaseId: number) => void;
  onLongPress?: (releaseId: number) => void;
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
  const { t } = useTranslation("wanted");
  const { release } = props;
  const platformsById = usePlatformsById();
  const platform = platformsById.get(release.platformId);
  const platformLabel =
    platform?.short_name?.trim() ||
    platform?.name ||
    null;

  const selectionActive = props.selectionActive ?? false;
  const selected = props.selected ?? false;

  const longPress = useLongPress(
    () => props.onLongPress?.(release.id),
    { disabled: selectionActive || props.onLongPress === undefined },
  );

  const className = [
    "flex flex-col gap-2 rounded-md border p-3 text-left",
    "bg-zinc-900/40",
    selected
      ? "border-brand ring-2 ring-brand/60 bg-brand/10"
      : "border-zinc-800 hover:border-brand/40 hover:bg-zinc-900",
    "focus-visible:outline-none focus-visible:ring-2",
    "focus-visible:ring-brand",
    "transition-colors",
  ].join(" ");

  const inner = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          {selectionActive && (
            <span
              aria-hidden="true"
              className={[
                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center",
                "rounded text-[0.65rem] ring-1 ring-inset",
                selected
                  ? "bg-brand text-zinc-950 ring-brand"
                  : "bg-zinc-950 text-zinc-600 ring-zinc-700",
              ].join(" ")}
            >
              {selected ? "✓" : ""}
            </span>
          )}
          <p className="truncate text-sm font-medium text-zinc-100">
            {release.name}
          </p>
        </div>
        {platformLabel && (
          <span
            className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-300"
            title={platform?.name ?? undefined}
          >
            {platformLabel}
          </span>
        )}
      </div>
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
    </>
  );

  if (selectionActive) {
    return (
      <button
        type="button"
        onClick={() => props.onToggleSelect?.(release.id)}
        aria-pressed={selected}
        aria-label={
          selected
            ? t("bulk.deselectAria", { name: release.name })
            : t("bulk.selectAria", { name: release.name })
        }
        className={className}
      >
        {inner}
      </button>
    );
  }

  return (
    <Link
      to={`/game/${release.gameId}`}
      className={className}
      style={{ touchAction: "manipulation" }}
      {...longPress}
    >
      {inner}
    </Link>
  );
}
