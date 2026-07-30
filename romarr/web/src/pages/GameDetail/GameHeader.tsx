/**
 * Compact game-detail header (slice 364).
 *
 * Layout:
 *   * cover on the left (small);
 *   * a "side rail" on the right of the cover with the
 *     platform pill, the year, and the four action buttons
 *     (Refresh metadata, Monitor, Search, Delete);
 *   * title + summary (line-clamped) span the full width below
 *     the cover/rail row on mobile; on ≥sm they sit to the
 *     right of the cover, with the rail ending up *under* the
 *     title to keep the action set near the top of the card.
 *
 * Cover is ``w-20 sm:w-24 md:w-28`` — half its previous size on
 * desktop. Summary is ``line-clamp-2 sm:line-clamp-3`` with
 * ``text-[0.7rem]`` so the description doesn't push the tab bar
 * below the fold.
 *
 * The page tab bar lives BELOW this whole block (slice 364),
 * sticky-top so it stays in reach as the operator scrolls.
 */

import { Check, Clock, Pencil, Search, ShieldCheck, Trash2 } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { CoverImage } from "@/components/rom";
import type { Game } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import { useTagsById } from "@/lib/api/queries/tags";

import { CoverEditModal } from "./CoverEditModal";
import {
  EditableSummary,
  EditableTitle,
  MonitorToggle,
  RefreshMetadataButton,
} from "./OverviewTab";

interface GameHeaderProps {
  game: Game;
  onEditClick: () => void;
  onSearchClick: () => void;
  onDeleteClick: () => void;
}

export function GameHeader(props: GameHeaderProps): ReactElement {
  const { t } = useTranslation("game");
  const { game, onEditClick, onSearchClick, onDeleteClick } = props;
  const platformsById = usePlatformsById();
  const platform = platformsById.get(game.platform_id);
  const platformLabel = platform
    ? platform.short_name ?? platform.name
    : `#${game.platform_id}`;
  const tagsById = useTagsById();
  const tagPills = (game.tags ?? [])
    .map((id) => tagsById.get(id))
    .filter((tag): tag is NonNullable<typeof tag> => tag !== undefined);

  const [coverEditOpen, setCoverEditOpen] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const coverLocked = (game.locked_fields ?? []).includes("cover");
  const hasSummary =
    game.summary !== null &&
    game.summary !== undefined &&
    game.summary.trim().length > 0;
  // Lower threshold than slice 364's first cut — anything past
  // ~120 chars overflows two lines at this typography, so we
  // surface the "Show more" toggle eagerly.
  const summaryNeedsToggle = hasSummary && (game.summary?.length ?? 0) > 120;
  const releaseYear = game.release_date
    ? new Date(game.release_date).getFullYear()
    : null;

  return (
    <header className="mb-3 rounded-md border border-zinc-800 bg-zinc-900/40 p-3 sm:p-4">
      <div className="flex items-start gap-3">
        {/* Cover — small. */}
        <button
          type="button"
          onClick={() => setCoverEditOpen(true)}
          aria-label={t("overview.cover.changeAria")}
          className={[
            "group relative block w-20 shrink-0 self-start rounded",
            "sm:w-24 md:w-28",
            "focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-brand",
          ].join(" ")}
        >
          <CoverImage
            gameId={game.id}
            src={game.cover_path ?? null}
            cacheKey={game.updated_at ?? null}
            alt={game.title}
            sizeClassName="aspect-[3/4] w-full"
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center rounded-b bg-zinc-950/70 py-0.5 text-[0.55rem] text-zinc-300 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            ✎ {t("overview.cover.changeShort")}
          </span>
          {coverLocked && (
            <span
              aria-hidden="true"
              title={t("overview.lock.lockedHint")}
              className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-zinc-950/80 text-[0.6rem] text-amber-400 ring-1 ring-inset ring-zinc-700 backdrop-blur-sm"
            >
              🔒
            </span>
          )}
          {/* Slice 447 — DAT-verified shield overlay on the
              cover so the operator sees the verification status
              at a glance, even before tabbing into Files. */}
          {(game.dat_verified_dump_count ?? 0) > 0 && (
            <span
              aria-hidden="true"
              title={t("header.datVerifiedTooltip", {
                count: game.dat_verified_dump_count ?? 0,
              })}
              className={[
                "absolute bottom-1 right-1 flex h-5 w-5 items-center justify-center",
                "rounded-full bg-emerald-700/85 text-emerald-100 ring-1 ring-inset ring-emerald-400/60",
                "backdrop-blur-sm",
              ].join(" ")}
            >
              <ShieldCheck size={12} strokeWidth={2.5} />
            </span>
          )}
        </button>

        {coverEditOpen && (
          <CoverEditModal
            game={game}
            onClose={() => setCoverEditOpen(false)}
          />
        )}

        {/* Right column: title, badges, actions. Summary lives
            below this row on every breakpoint so a long
            description never crowds the action buttons. */}
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="min-w-0">
            <EditableTitle game={game} />
          </div>

          {/* Platform + year + first few tags as compact pills. */}
          <div className="flex flex-wrap items-center gap-1 text-[0.6rem]">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono uppercase tracking-wider text-zinc-300">
              {platformLabel}
            </span>
            {releaseYear !== null && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-zinc-400">
                {releaseYear}
              </span>
            )}
            {/* Slice 395 — acquired / wanted status pill. */}
            {game.acquired ? (
              <span
                title={t("header.status.acquiredTooltip")}
                className="inline-flex items-center gap-0.5 rounded-full bg-emerald-700/30 px-1.5 py-0.5 font-medium text-emerald-200 ring-1 ring-inset ring-emerald-500/40"
              >
                <Check size={10} strokeWidth={3} aria-hidden="true" />
                {t("header.status.acquired")}
              </span>
            ) : game.monitored ? (
              <span
                title={t("header.status.wantedTooltip")}
                className="inline-flex items-center gap-0.5 rounded-full bg-amber-700/30 px-1.5 py-0.5 font-medium text-amber-200 ring-1 ring-inset ring-amber-500/40"
              >
                <Clock size={10} strokeWidth={2.5} aria-hidden="true" />
                {t("header.status.wanted")}
              </span>
            ) : null}
            {(game.dat_verified_dump_count ?? 0) > 0 && (
              <span
                title={t("header.datVerifiedTooltip", {
                  count: game.dat_verified_dump_count ?? 0,
                })}
                className="inline-flex items-center gap-0.5 rounded-full bg-emerald-700/30 px-1.5 py-0.5 font-medium text-emerald-200 ring-1 ring-inset ring-emerald-500/40"
              >
                <ShieldCheck size={10} strokeWidth={2.5} aria-hidden="true" />
                {t("header.datVerifiedPill", {
                  count: game.dat_verified_dump_count ?? 0,
                })}
              </span>
            )}
            {game.publisher && (
              <span className="truncate text-zinc-500">{game.publisher}</span>
            )}
            {tagPills.slice(0, 2).map((tag) => (
              <span
                key={tag.id}
                className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 ring-1 ring-inset ring-zinc-700"
                style={{
                  backgroundColor: `${tag.color}20`,
                  color: tag.color,
                }}
              >
                <span
                  aria-hidden="true"
                  className="block h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: tag.color }}
                />
                {tag.label}
              </span>
            ))}
          </div>

          {/* Actions — Refresh, Monitor, Search, Delete — sit
              right under the title pills so they're the first
              thing the operator's thumb reaches. All four
              buttons share the same height/typography so the
              row scans as a single control group. */}
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            <RefreshMetadataButton game={game} />
            <MonitorToggle game={game} />
            <button
              type="button"
              onClick={onEditClick}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-[0.7rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <Pencil size={12} aria-hidden="true" />
              {t("edit.button")}
            </button>
            <button
              type="button"
              onClick={onSearchClick}
              className="inline-flex items-center gap-1 rounded-md border border-brand/60 bg-brand/10 px-2.5 py-1 text-[0.7rem] font-medium text-brand hover:bg-brand/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <Search size={12} aria-hidden="true" />
              {t("search.headerButton")}
            </button>
            <button
              type="button"
              onClick={onDeleteClick}
              className="inline-flex items-center gap-1 rounded-md border border-red-700/60 px-2.5 py-1 text-[0.7rem] font-medium text-red-300 hover:bg-red-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              <Trash2 size={12} aria-hidden="true" />
              {t("delete.button")}
            </button>
          </div>
        </div>
      </div>

      {/* Summary spans the full card width below the cover/rail
          row. The line-clamp class is passed directly to the
          ``<p>`` *inside* EditableSummary — applying it on a
          wrapper ``<div>`` doesn't propagate because
          ``-webkit-line-clamp`` only works on the text element
          itself. ``line-clamp-1 sm:line-clamp-2`` keeps the
          description to a couple of lines even on a phone; the
          operator clicks "Show more" to expand. */}
      {hasSummary && (
        <div className="mt-3 space-y-1">
          <EditableSummary
            game={game}
            textClassName={[
              "text-[0.7rem] leading-relaxed",
              summaryExpanded ? "" : "line-clamp-1 sm:line-clamp-2",
            ]
              .join(" ")
              .trim()}
          />
          {summaryNeedsToggle && (
            <button
              type="button"
              onClick={() => setSummaryExpanded((v) => !v)}
              className="text-[0.6rem] text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {summaryExpanded
                ? t("header.summary.showLess")
                : t("header.summary.showMore")}
            </button>
          )}
        </div>
      )}
    </header>
  );
}
