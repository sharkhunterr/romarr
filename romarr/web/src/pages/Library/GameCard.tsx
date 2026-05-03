/**
 * Single game card (slice 88).
 *
 * Used by the Library grid. Cover (gradient fallback when
 * `cover_path` is null or no covers endpoint is configured),
 * title, platform-id pill, click-through to /game/{id}
 * (still a placeholder until the GameDetail page ships).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { CoverImage } from "@/components/rom";
import type { Game } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import { useTagsById } from "@/lib/api/queries/tags";

interface GameCardProps {
  game: Game;
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

  return (
    <Link
      to={`/game/${game.id}`}
      className={[
        "group relative flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-2",
        "hover:border-brand/40 hover:bg-zinc-900",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "transition-colors",
      ].join(" ")}
      aria-label={
        game.monitored
          ? game.title
          : t("card.unmonitoredAria", { title: game.title })
      }
    >
      <div className="relative">
        <CoverImage
          src={game.cover_path ?? null}
          alt={game.title}
          sizeClassName="aspect-[3/4] w-full"
        />
        {!game.monitored && (
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
            "group-hover:text-brand",
            game.monitored ? "text-zinc-100" : "text-zinc-400",
          ].join(" ")}
        >
          {game.title}
        </p>
        <div className="flex items-center justify-between gap-1 font-mono text-[0.55rem] text-zinc-500">
          <span
            className="truncate rounded bg-zinc-800 px-1.5 py-0.5 uppercase tracking-wider"
            title={platform?.name ?? `P#${game.platform_id}`}
          >
            {platformLabel}
          </span>
          <span className="shrink-0">#{game.id}</span>
        </div>
      </div>
    </Link>
  );
}
