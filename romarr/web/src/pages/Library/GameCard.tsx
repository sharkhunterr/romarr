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

interface GameCardProps {
  game: Game;
}

export function GameCard(props: GameCardProps): ReactElement {
  const { t } = useTranslation("library");
  const { game } = props;
  const byId = usePlatformsById();
  const platform = byId.get(game.platform_id);
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
