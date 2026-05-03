/**
 * Library page (P-LIB, slice 88; slice 100 adds platform filter).
 *
 * Grid of every game from /api/v3/game. Title-substring search
 * is debounced 200 ms; the platform filter (slice 100) reuses
 * the existing `platform_id` query param on the same endpoint
 * and reads its option list from the new `usePlatforms` hook
 * (slice 99).
 *
 * Filters still deferred to follow-up slices:
 *   * Region / quality / dump status / monitored — need
 *     additional joins / index columns on the Game/Release
 *     surface.
 */

import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { CardGridSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useGames,
  type GameSortKey,
  type ListGamesParams,
  type SortDirection,
} from "@/lib/api/queries/games";
import { usePlatforms } from "@/lib/api/queries/platforms";

import { GameCard } from "./GameCard";

const ALL_PLATFORMS = "all" as const;
const SORT_KEYS: readonly GameSortKey[] = [
  "title",
  "added_at",
  "release_date",
  "rating",
];
const SORT_KEY_SET: ReadonlySet<GameSortKey> = new Set<GameSortKey>(SORT_KEYS);

type PlatformFilterValue = number | typeof ALL_PLATFORMS;

function parsePlatformParam(raw: string | null): PlatformFilterValue {
  if (raw === null || raw === "") return ALL_PLATFORMS;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : ALL_PLATFORMS;
}

function parseSortParam(raw: string | null): GameSortKey {
  return raw !== null && SORT_KEY_SET.has(raw as GameSortKey)
    ? (raw as GameSortKey)
    : "title";
}

function parseDirectionParam(raw: string | null): SortDirection {
  return raw === "desc" ? "desc" : "asc";
}

export function LibraryPage(): ReactElement {
  const { t } = useTranslation("library");
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const platformFilter = parsePlatformParam(searchParams.get("platform"));
  const sortKey = parseSortParam(searchParams.get("sort"));
  const sortDirection = parseDirectionParam(searchParams.get("direction"));

  const setPlatformFilter = (next: PlatformFilterValue): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === ALL_PLATFORMS) params.delete("platform");
        else params.set("platform", String(next));
        return params;
      },
      { replace: false },
    );
  };

  const setSortKey = (next: GameSortKey): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "title") params.delete("sort");
        else params.set("sort", next);
        return params;
      },
      { replace: false },
    );
  };

  const toggleSortDirection = (): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        const next = sortDirection === "asc" ? "desc" : "asc";
        if (next === "asc") params.delete("direction");
        else params.set("direction", next);
        return params;
      },
      { replace: false },
    );
  };

  useEffect(() => {
    const handle = window.setTimeout(
      () => setDebouncedQuery(query.trim()),
      200,
    );
    return () => window.clearTimeout(handle);
  }, [query]);

  const platforms = usePlatforms();

  const params: ListGamesParams = useMemo(() => {
    const out: ListGamesParams = {
      limit: 200,
      sort: sortKey,
      direction: sortDirection,
    };
    if (debouncedQuery.length > 0) out.q = debouncedQuery;
    if (platformFilter !== ALL_PLATFORMS) out.platformId = platformFilter;
    return out;
  }, [debouncedQuery, platformFilter, sortKey, sortDirection]);

  const games = useGames(params);

  const filtersActive =
    debouncedQuery.length > 0 || platformFilter !== ALL_PLATFORMS;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6 space-y-3">
        <div>
          <h1 className="font-mono text-xl font-semibold text-brand">
            {t("title")}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
        </div>

        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <label className="block flex-1">
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

          <label className="block md:w-56">
            <span className="sr-only">{t("filters.platform.label")}</span>
            <select
              value={platformFilter === ALL_PLATFORMS ? "" : String(platformFilter)}
              onChange={(e) => {
                const v = e.target.value;
                setPlatformFilter(
                  v === "" ? ALL_PLATFORMS : Number.parseInt(v, 10),
                );
              }}
              aria-label={t("filters.platform.label")}
              disabled={!platforms.isSuccess}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              <option value="">{t("filters.platform.all")}</option>
              {platforms.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-stretch gap-1">
            <label className="block md:w-44">
              <span className="sr-only">{t("sort.label")}</span>
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as GameSortKey)}
                aria-label={t("sort.label")}
                className={[
                  "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                  "ring-1 ring-inset ring-zinc-700",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                ].join(" ")}
              >
                {SORT_KEYS.map((k) => (
                  <option key={k} value={k}>
                    {t(`sort.key.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={toggleSortDirection}
              aria-label={
                sortDirection === "asc"
                  ? t("sort.direction.asc")
                  : t("sort.direction.desc")
              }
              title={
                sortDirection === "asc"
                  ? t("sort.direction.asc")
                  : t("sort.direction.desc")
              }
              className={[
                "rounded-md bg-zinc-950 px-3 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {sortDirection === "asc" ? "↑" : "↓"}
            </button>
          </div>
        </div>

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
            filtersActive ? t("noResults.title") : t("empty.title")
          }
          description={
            filtersActive
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
