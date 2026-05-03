/**
 * Single game card (slice 88).
 *
 * Used by the Library grid. Cover (gradient fallback when
 * `cover_path` is null or no covers endpoint is configured),
 * title, platform-id pill, click-through to /game/{id}
 * (still a placeholder until the GameDetail page ships).
 */

import { type ReactElement } from "react";
import { Link } from "react-router-dom";

import { CoverImage } from "@/components/rom";
import type { Game } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";

interface GameCardProps {
  game: Game;
}

export function GameCard(props: GameCardProps): ReactElement {
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
        "group flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-2",
        "hover:border-brand/40 hover:bg-zinc-900",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "transition-colors",
      ].join(" ")}
    >
      <CoverImage
        src={game.cover_path ?? null}
        alt={game.title}
        sizeClassName="aspect-[3/4] w-full"
      />
      <div className="min-w-0 space-y-1">
        <p className="line-clamp-2 text-xs font-medium text-zinc-100 group-hover:text-brand">
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
