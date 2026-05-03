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

interface GameCardProps {
  game: Game;
}

export function GameCard(props: GameCardProps): ReactElement {
  const { game } = props;
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
        <div className="flex items-center justify-between font-mono text-[0.55rem] text-zinc-500">
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 uppercase tracking-wider">
            P#{game.platform_id}
          </span>
          <span>#{game.id}</span>
        </div>
      </div>
    </Link>
  );
}
