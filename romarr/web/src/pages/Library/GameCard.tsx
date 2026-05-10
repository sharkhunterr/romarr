/**
 * Single game card (slices 88, 151, 158).
 *
 * Used by the Library grid. Cover (gradient fallback when
 * `cover_path` is null or no covers endpoint is configured),
 * title, platform-id pill, click-through to /game/{id}.
 *
 * In bulk-select mode (``selectionActive=true``) the card
 * becomes a button — clicking toggles selection instead of
 * navigating to the detail page; a ✓ overlay marks selected
 * cards and the border lights up brand-tinted.
 *
 * On mobile, holding a card for ~500 ms (long-press) fires
 * ``onLongPress`` so the parent can flip into selection mode
 * and pre-select the held card — matches the spec D
 * "long-press for multi-select on Library and Wanted" rule.
 */

import { Check, Clock } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { CoverImage } from "@/components/rom";
import type { Game } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import { useTagsById } from "@/lib/api/queries/tags";
import { useLongPress } from "@/lib/hooks/useLongPress";

interface GameCardProps {
  game: Game;
  selectionActive?: boolean;
  selected?: boolean;
  onToggleSelect?: (gameId: number) => void;
  /** Fires when the operator long-presses (~500 ms). Parents
   * use this to enter bulk-select mode + pre-select the card. */
  onLongPress?: (gameId: number) => void;
}

export function GameCard(props: GameCardProps): ReactElement {
  const { t } = useTranslation("library");
  const { game } = props;
  const byId = usePlatformsById();
  const platform = byId.get(game.platform_id);
  const tagsById = useTagsById();
  const tagIds = game.tags ?? [];
  // Resolve up to MAX_DOTS distinct tag colours. Anything beyond
  // becomes a "+N" pill so the card stays compact at the 360-px
  // mobile-first viewport.
  const MAX_DOTS = 4;
  const dots = tagIds
    .map((id) => tagsById.get(id))
    .filter((tag): tag is NonNullable<typeof tag> => tag !== undefined)
    .slice(0, MAX_DOTS);
  const overflowCount = tagIds.length - dots.length;
  // Prefer the short name when present (e.g. "MD" over
  // "Mega Drive") since the card is space-constrained on mobile.
  const platformLabel =
    platform?.short_name?.trim() ||
    platform?.name ||
    `P#${game.platform_id}`;

  const selectionActive = props.selectionActive ?? false;
  const selected = props.selected ?? false;

  const longPress = useLongPress(
    () => props.onLongPress?.(game.id),
    { disabled: selectionActive || props.onLongPress === undefined },
  );

  const cardClassName = [
    "group relative flex flex-col gap-2 rounded-md border p-2 text-left",
    "bg-zinc-900/40",
    selected
      ? "border-brand ring-2 ring-brand/60 bg-brand/10"
      : "border-zinc-800 hover:border-brand/40 hover:bg-zinc-900",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
    "transition-colors",
  ].join(" ");

  const ariaLabel = selectionActive
    ? selected
      ? t("card.deselectAria", { title: game.title })
      : t("card.selectAria", { title: game.title })
    : game.monitored
      ? game.title
      : t("card.unmonitoredAria", { title: game.title });

  const inner = (
    <>
      <div className="relative">
        <CoverImage
          gameId={game.id}
          src={game.cover_path ?? null}
          cacheKey={game.updated_at ?? null}
          alt={game.title}
          sizeClassName="aspect-[3/4] w-full"
        />
        {selectionActive && (
          <span
            aria-hidden="true"
            className={[
              "absolute left-1 top-1 flex h-5 w-5 items-center justify-center",
              "rounded-md text-[0.7rem] ring-1 ring-inset",
              selected
                ? "bg-brand text-zinc-950 ring-brand"
                : "bg-zinc-950/80 text-zinc-500 ring-zinc-700",
              "backdrop-blur-sm",
            ].join(" ")}
          >
            {selected ? "✓" : ""}
          </span>
        )}
        {/* Slice 395 — acquired / wanted / unmonitored badge.
            Mutual ranking: acquired wins (file is there), then
            wanted (monitored but missing), then unmonitored. */}
        {game.acquired ? (
          <span
            title={t("card.acquiredTooltip")}
            aria-label={t("card.acquiredAria")}
            className={[
              "absolute right-1 top-1 flex h-5 w-5 items-center justify-center",
              "rounded-full bg-emerald-600/90 text-zinc-950 ring-1 ring-inset ring-emerald-400/60",
              "backdrop-blur-sm",
            ].join(" ")}
          >
            <Check size={11} strokeWidth={3} aria-hidden="true" />
          </span>
        ) : game.monitored ? (
          <span
            title={t("card.wantedTooltip")}
            aria-label={t("card.wantedAria")}
            className={[
              "absolute right-1 top-1 flex h-5 w-5 items-center justify-center",
              "rounded-full bg-amber-500/90 text-zinc-950 ring-1 ring-inset ring-amber-300/60",
              "backdrop-blur-sm",
            ].join(" ")}
          >
            <Clock size={11} strokeWidth={2.5} aria-hidden="true" />
          </span>
        ) : (
          <span
            aria-hidden="true"
            title={t("card.unmonitoredTooltip")}
            className={[
              "absolute right-1 top-1 flex h-5 w-5 items-center justify-center",
              "rounded-full bg-zinc-950/80 text-[0.7rem] ring-1 ring-inset ring-zinc-700",
              "backdrop-blur-sm",
            ].join(" ")}
          >
            💤
          </span>
        )}
        {(dots.length > 0 || overflowCount > 0) && (
          <div
            className={[
              "absolute bottom-1 left-1 flex items-center gap-0.5",
              "rounded-full bg-zinc-950/80 px-1 py-0.5 ring-1 ring-inset ring-zinc-700",
              "backdrop-blur-sm",
            ].join(" ")}
            aria-label={t("card.tagsAria", { count: tagIds.length })}
          >
            {dots.map((tag) => (
              <span
                key={tag.id}
                aria-hidden="true"
                title={tag.label}
                className="block h-2 w-2 rounded-full ring-1 ring-zinc-950/40"
                style={{ backgroundColor: tag.color }}
              />
            ))}
            {overflowCount > 0 && (
              <span
                className="font-mono text-[0.55rem] text-zinc-300"
                aria-hidden="true"
              >
                +{overflowCount}
              </span>
            )}
          </div>
        )}
      </div>
      <div className="min-w-0 space-y-1">
        <p
          className={[
            "line-clamp-2 text-xs font-medium",
            selectionActive ? "" : "group-hover:text-brand",
            game.monitored ? "text-zinc-100" : "text-zinc-400",
          ].join(" ")}
        >
          {game.title}
        </p>
        <div className="flex items-center justify-between gap-1 font-mono text-[0.55rem] text-zinc-500">
          <span
            className="min-w-0 truncate rounded bg-zinc-800 px-1.5 py-0.5 uppercase tracking-wider"
            title={platform?.name ?? `P#${game.platform_id}`}
          >
            {platformLabel}
          </span>
          <span className="shrink-0">#{game.id}</span>
        </div>
      </div>
    </>
  );

  if (selectionActive) {
    return (
      <button
        type="button"
        onClick={() => props.onToggleSelect?.(game.id)}
        aria-pressed={selected}
        aria-label={ariaLabel}
        className={cardClassName}
      >
        {inner}
      </button>
    );
  }

  return (
    <Link
      to={`/game/${game.id}`}
      className={cardClassName}
      aria-label={ariaLabel}
      style={{ touchAction: "manipulation" }}
      {...longPress}
    >
      {inner}
    </Link>
  );
}
