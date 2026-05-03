/**
 * Library page (P-LIB, slices 88, 100, 151).
 *
 * Grid of every game from /api/v3/game. Title-substring search
 * is debounced 200 ms; the platform filter (slice 100) reuses
 * the existing `platform_id` query param on the same endpoint
 * and reads its option list from the new `usePlatforms` hook
 * (slice 99).
 *
 * Slice 151 adds a bulk-select mode: hit "Select" to enter,
 * tap cards to toggle selection, then hit Monitor / Unmonitor
 * to flip the flag on every selected Game in one batch via
 * /api/v3/game/bulk-monitor.
 */

import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { CardGridSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useBulkMonitorGames,
  useGames,
  type GameSortKey,
  type ListGamesParams,
  type SortDirection,
} from "@/lib/api/queries/games";
import { usePlatforms } from "@/lib/api/queries/platforms";
import { useToastStore } from "@/lib/store/toast";

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
  const urlQuery = searchParams.get("q") ?? "";
  // Local input state seeded from the URL on mount; debounced
  // commits write back to the URL so the API call key (and the
  // shareable link) only updates once the operator pauses.
  const [query, setQuery] = useState(urlQuery);
  const platformFilter = parsePlatformParam(searchParams.get("platform"));
  const monitoredOnly = searchParams.get("monitoredOnly") === "true";
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

  const setMonitoredOnly = (next: boolean): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next) params.set("monitoredOnly", "true");
        else params.delete("monitoredOnly");
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

  // Debounce the URL write — keystrokes don't pollute history,
  // and the API key (and shareable link) settles 200 ms after
  // the operator stops typing.
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed === urlQuery) return;
    const handle = window.setTimeout(() => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmed === "") next.delete("q");
          else next.set("q", trimmed);
          return next;
        },
        { replace: true },
      );
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, urlQuery, setSearchParams]);

  const platforms = usePlatforms();

  const params: ListGamesParams = useMemo(() => {
    const out: ListGamesParams = {
      limit: 200,
      sort: sortKey,
      direction: sortDirection,
    };
    if (urlQuery.length > 0) out.q = urlQuery;
    if (platformFilter !== ALL_PLATFORMS) out.platformId = platformFilter;
    if (monitoredOnly) out.monitored = true;
    return out;
  }, [urlQuery, platformFilter, monitoredOnly, sortKey, sortDirection]);

  const games = useGames(params);

  const filtersActive =
    urlQuery.length > 0 ||
    platformFilter !== ALL_PLATFORMS ||
    monitoredOnly;

  // -- Bulk select state (slice 151) ----------------------------------------
  const pushToast = useToastStore((s) => s.push);
  const bulkMonitor = useBulkMonitorGames();
  const [selectionActive, setSelectionActive] = useState(false);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );

  const exitSelection = (): void => {
    setSelectionActive(false);
    setSelectedIds(new Set());
  };

  const toggleSelect = (gameId: number): void => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(gameId)) next.delete(gameId);
      else next.add(gameId);
      return next;
    });
  };

  const selectAllVisible = (): void => {
    if (!games.data) return;
    setSelectedIds(new Set(games.data.map((g) => g.id)));
  };

  const runBulkMonitor = (monitored: boolean): void => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    bulkMonitor.mutate(
      { gameIds: ids, monitored },
      {
        onSuccess: (resp) => {
          pushToast({
            kind: "success",
            title: monitored
              ? t("bulk.monitor.successTitle")
              : t("bulk.unmonitor.successTitle"),
            description: t("bulk.monitor.successBody", {
              updated: resp.updated,
              missing: resp.missing.length,
            }),
          });
          exitSelection();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("bulk.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  };

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

          <button
            type="button"
            onClick={() => setMonitoredOnly(!monitoredOnly)}
            aria-pressed={monitoredOnly}
            className={[
              "shrink-0 rounded-md px-3 py-2 text-xs font-medium ring-1 ring-inset",
              "transition-colors",
              monitoredOnly
                ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
                : "bg-zinc-950 text-zinc-400 ring-zinc-700 hover:bg-zinc-900",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {monitoredOnly
              ? t("filters.monitoredOnly.on")
              : t("filters.monitoredOnly.off")}
          </button>

          <button
            type="button"
            onClick={() =>
              selectionActive ? exitSelection() : setSelectionActive(true)
            }
            aria-pressed={selectionActive}
            className={[
              "shrink-0 rounded-md px-3 py-2 text-xs font-medium ring-1 ring-inset",
              "transition-colors",
              selectionActive
                ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
                : "bg-zinc-950 text-zinc-400 ring-zinc-700 hover:bg-zinc-900",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {selectionActive
              ? t("bulk.exitSelection")
              : t("bulk.enterSelection")}
          </button>
        </div>

        {selectionActive && (
          <div
            role="region"
            aria-label={t("bulk.toolbarAria")}
            className="flex flex-wrap items-center gap-2 rounded-md border border-brand/40 bg-brand/10 px-3 py-2"
          >
            <p className="text-xs text-zinc-100">
              {t("bulk.selectedCount", { count: selectedIds.size })}
            </p>
            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={selectAllVisible}
                disabled={!games.data || games.data.length === 0}
                className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t("bulk.selectAll")}
              </button>
              <button
                type="button"
                onClick={() => runBulkMonitor(true)}
                disabled={selectedIds.size === 0 || bulkMonitor.isPending}
                className="rounded-md bg-emerald-600 px-2 py-1 text-[0.65rem] font-medium text-zinc-950 hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {bulkMonitor.isPending
                  ? t("bulk.monitor.pending")
                  : t("bulk.monitor.label")}
              </button>
              <button
                type="button"
                onClick={() => runBulkMonitor(false)}
                disabled={selectedIds.size === 0 || bulkMonitor.isPending}
                className="rounded-md bg-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-100 hover:bg-zinc-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                {bulkMonitor.isPending
                  ? t("bulk.unmonitor.pending")
                  : t("bulk.unmonitor.label")}
              </button>
              <button
                type="button"
                onClick={exitSelection}
                disabled={bulkMonitor.isPending}
                className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t("bulk.cancel")}
              </button>
            </div>
          </div>
        )}

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
              ? t("noResults.body", { q: urlQuery })
              : t("empty.body")
          }
        />
      )}

      {games.isSuccess && games.data.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {games.data.map((game) => (
            <li key={game.id}>
              <GameCard
                game={game}
                selectionActive={selectionActive}
                selected={selectedIds.has(game.id)}
                onToggleSelect={toggleSelect}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
