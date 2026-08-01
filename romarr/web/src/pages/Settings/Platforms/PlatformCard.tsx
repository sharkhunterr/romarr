/**
 * One platform in the catalogue grid.
 *
 * Compact single-card layout with a clear hierarchy :
 *
 *   Line 1 : name              [S1] [S2] …    (source badges, right-aligned)
 *   Line 2 : short_name · slug · manufacturer · year
 *   Line 3 (if aliases) : first two aliases + "+ N more"
 *
 * Clicking the card opens the detail modal.
 */

import { Layers } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { Platform } from "@/lib/api/queries/platforms";

interface Props {
  platform: Platform;
  /** Map of source id → source name for badge tooltips. */
  sourceNames: Map<number, string>;
  onClick: () => void;
}

// Deterministic per-source-id colour, so the same source always
// gets the same badge tint across every card in the grid.
const BADGE_PALETTE = [
  "border-brand/50 bg-brand/10 text-brand",
  "border-sky-800/60 bg-sky-950/40 text-sky-300",
  "border-fuchsia-800/60 bg-fuchsia-950/40 text-fuchsia-300",
  "border-emerald-800/60 bg-emerald-950/40 text-emerald-300",
  "border-orange-800/60 bg-orange-950/40 text-orange-300",
  "border-cyan-800/60 bg-cyan-950/40 text-cyan-300",
];

function paletteFor(sourceId: number): string {
  return BADGE_PALETTE[sourceId % BADGE_PALETTE.length]!;
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[1]![0]!).toUpperCase();
}

export function PlatformCard(props: Props): ReactElement {
  const { platform: p, sourceNames, onClick } = props;
  const { t } = useTranslation("settings");

  const contributors = p.contributing_source_ids ?? [];
  const aliases = (p.aliases ?? []).filter(Boolean);
  const shownAliases = aliases.slice(0, 2);
  const remainingAliases = aliases.length - shownAliases.length;

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-full w-full flex-col gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-left transition-colors hover:border-brand/40 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      {/* Line 1 : name + source badges */}
      <div className="flex items-start gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-zinc-100">
          {p.name}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {contributors.length === 0 && (
            <span
              className="rounded border border-zinc-700 bg-zinc-800/60 px-1.5 py-px text-[0.55rem] uppercase tracking-wider text-zinc-500"
              title={t("platforms.card.noSource")}
            >
              —
            </span>
          )}
          {contributors.slice(0, 3).map((id) => {
            const name = sourceNames.get(id) ?? `#${id}`;
            return (
              <span
                key={id}
                className={`inline-flex h-4 min-w-[1.25rem] items-center justify-center rounded border px-1 text-[0.55rem] font-semibold ${paletteFor(id)}`}
                title={t("platforms.card.sourceTooltip", { name })}
              >
                {initialsFor(name)}
              </span>
            );
          })}
          {contributors.length > 3 && (
            <span
              className="inline-flex h-4 items-center rounded border border-zinc-700 bg-zinc-800/60 px-1 text-[0.55rem] font-medium text-zinc-400"
              title={t("platforms.card.moreSources", {
                count: contributors.length - 3,
              })}
            >
              +{contributors.length - 3}
            </span>
          )}
        </div>
      </div>

      {/* Line 2 : short_name · slug · manufacturer · year */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.65rem] text-zinc-500">
        {p.short_name && (
          <span className="rounded bg-zinc-800/60 px-1.5 py-px text-[0.6rem] font-medium text-zinc-300">
            {p.short_name}
          </span>
        )}
        <span className="truncate font-mono">{p.slug}</span>
        {p.manufacturer && (
          <>
            <span className="text-zinc-700">·</span>
            <span className="truncate">{p.manufacturer}</span>
          </>
        )}
        {p.release_year && (
          <>
            <span className="text-zinc-700">·</span>
            <span className="tabular-nums">{p.release_year}</span>
          </>
        )}
      </div>

      {/* Line 3 : aliases summary */}
      {aliases.length > 0 && (
        <div className="mt-0.5 flex items-center gap-1 text-[0.6rem] text-zinc-500">
          <Layers size={10} aria-hidden="true" />
          <span className="truncate">
            {shownAliases.join(", ")}
            {remainingAliases > 0 && (
              <span className="text-zinc-600">
                {" "}
                +{remainingAliases}
              </span>
            )}
          </span>
        </div>
      )}
    </button>
  );
}
