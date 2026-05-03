/**
 * Recent Additions section for the AddNew page (slice 148).
 *
 * Surfaces the 10 most recently added games (sort=added_at,
 * direction=desc) so the operator can confirm their adds
 * landed and quickly jump back to one whose metadata is still
 * refreshing.
 *
 * Strings resolve through the ``addNew`` namespace.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useGames } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import { formatRelativeTime } from "@/lib/i18n/dates";

const RECENT_LIMIT = 10;

export function RecentAdditions(): ReactElement | null {
  const { t, i18n } = useTranslation("addNew");
  const games = useGames({
    sort: "added_at",
    direction: "desc",
    limit: RECENT_LIMIT,
  });
  const byId = usePlatformsById();

  if (games.isPending) {
    return (
      <section className="mt-8 space-y-2">
        <h2 className="text-[0.65rem] font-semibold uppercase tracking-widest text-zinc-500">
          {t("recent.title")}
        </h2>
        <p className="text-[0.7rem] text-zinc-500">{t("recent.loading")}</p>
      </section>
    );
  }

  if (games.isError) {
    return (
      <section className="mt-8 space-y-2">
        <h2 className="text-[0.65rem] font-semibold uppercase tracking-widest text-zinc-500">
          {t("recent.title")}
        </h2>
        <p className="text-[0.7rem] text-red-400">{games.error.message}</p>
      </section>
    );
  }

  if (games.data.length === 0) {
    // Hide the section entirely when the library is empty —
    // surfacing an empty list under "Recent Additions" reads
    // worse than just hiding it.
    return null;
  }

  return (
    <section className="mt-8 space-y-2">
      <h2 className="text-[0.65rem] font-semibold uppercase tracking-widest text-zinc-500">
        {t("recent.title")}
      </h2>
      <ul className="divide-y divide-zinc-800 rounded-md border border-zinc-800 bg-zinc-900/40">
        {games.data.map((game) => {
          const platform = byId.get(game.platform_id);
          const platformLabel = platform?.name ?? `#${game.platform_id}`;
          const added = formatRelativeTime(
            game.created_at,
            i18n.resolvedLanguage,
          );
          return (
            <li key={game.id}>
              <Link
                to={`/game/${game.id}`}
                className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-zinc-900 focus-visible:bg-zinc-900 focus-visible:outline-none"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-zinc-100">
                    {game.title}
                  </p>
                  <p className="truncate text-[0.65rem] text-zinc-500">
                    {platformLabel}
                    {game.needs_metadata_refresh && (
                      <>
                        {" · "}
                        <span className="text-amber-400">
                          {t("recent.refreshing")}
                        </span>
                      </>
                    )}
                  </p>
                </div>
                {added !== "" && (
                  <time
                    dateTime={game.created_at}
                    className="shrink-0 font-mono text-[0.6rem] text-zinc-500"
                  >
                    {added}
                  </time>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
