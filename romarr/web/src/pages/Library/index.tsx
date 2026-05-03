/**
 * Library page (P-LIB, slice 88).
 *
 * MVP grid of every game from /api/v3/game (slice 86).
 * Title-substring search debounced 200 ms so we don't
 * pollute the query cache with every keystroke.
 *
 * Filters deferred to follow-up slices:
 *   * Platform — needs a platform-list endpoint.
 *   * Region / quality / dump status / monitored — need
 *     additional joins / index columns on the Game/Release
 *     surface.
 *
 * Click-through routes to /game/{id} which is still a
 * placeholder pending the P-GAME slice.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { CardGridSkeleton } from "@/components/shared/LoadingSkeleton";
import { useGames } from "@/lib/api/queries/games";

import { GameCard } from "./GameCard";

export function LibraryPage(): ReactElement {
  const { t } = useTranslation("library");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(
      () => setDebouncedQuery(query.trim()),
      200,
    );
    return () => window.clearTimeout(handle);
  }, [query]);

  const games = useGames(
    debouncedQuery.length > 0
      ? { q: debouncedQuery, limit: 200 }
      : { limit: 200 },
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6 space-y-3">
        <div>
          <h1 className="font-mono text-xl font-semibold text-brand">
            {t("title")}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
        </div>

        <label className="block">
          <span className="sr-only">{t("search.label")}</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("search.placeholder")}
            aria-label={t("search.label")}
            className={[
              "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
        </label>

        {games.isSuccess && (
          <p className="font-mono text-[0.65rem] text-zinc-500">
            {t("count", { count: games.data.length })}
          </p>
        )}
      </header>

      {games.isLoading && <CardGridSkeleton cards={12} />}

      {games.isError && (
        <EmptyState
          title={t("loadError")}
          description={games.error.message}
        />
      )}

      {games.isSuccess && games.data.length === 0 && (
        <EmptyState
          title={
            debouncedQuery.length > 0
              ? t("noResults.title")
              : t("empty.title")
          }
          description={
            debouncedQuery.length > 0
              ? t("noResults.body", { q: debouncedQuery })
              : t("empty.body")
          }
        />
      )}

      {games.isSuccess && games.data.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {games.data.map((game) => (
            <li key={game.id}>
              <GameCard game={game} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
