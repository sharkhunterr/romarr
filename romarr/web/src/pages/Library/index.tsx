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

import { ArrowDown, ArrowUp } from "lucide-react";
import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { CardGridSkeleton } from "@/components/shared/LoadingSkeleton";
import { VirtualGrid } from "@/components/shared/VirtualGrid";
import {
  useBulkMonitorGames,
  useGames,
  type GameSortKey,
  type ListGamesParams,
  type SortDirection,
} from "@/lib/api/queries/games";
import { useLibraries } from "@/lib/api/queries/libraries";
import { usePlatforms } from "@/lib/api/queries/platforms";
import { useTags } from "@/lib/api/queries/tags";
import { useToastStore } from "@/lib/store/toast";

import { LinkFAB } from "@/components/shared/FAB";

import { BulkDeleteModal } from "./BulkDeleteModal";
import { BulkTagModal } from "./BulkTagModal";
import { GameCard } from "./GameCard";

const ALL_PLATFORMS = "all" as const;
const ALL_TAGS = "all" as const;
const ALL_LIBRARIES = "all" as const;
const SORT_KEYS: readonly GameSortKey[] = [
  "title",
  "added_at",
  "release_date",
  "rating",
];
const SORT_KEY_SET: ReadonlySet<GameSortKey> = new Set<GameSortKey>(SORT_KEYS);

type PlatformFilterValue = number | typeof ALL_PLATFORMS;
type TagFilterValue = number | typeof ALL_TAGS;
type LibraryFilterValue = number | typeof ALL_LIBRARIES;

function parsePlatformParam(raw: string | null): PlatformFilterValue {
  if (raw === null || raw === "") return ALL_PLATFORMS;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : ALL_PLATFORMS;
}

function parseTagParam(raw: string | null): TagFilterValue {
  if (raw === null || raw === "") return ALL_TAGS;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : ALL_TAGS;
}

function parseLibraryParam(raw: string | null): LibraryFilterValue {
  if (raw === null || raw === "") return ALL_LIBRARIES;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : ALL_LIBRARIES;
}

function parseSortParam(raw: string | null): GameSortKey {
  return raw !== null && SORT_KEY_SET.has(raw as GameSortKey)
    ? (raw as GameSortKey)
    : "title";
}

function parseDirectionParam(raw: string | null): SortDirection {
  return raw === "desc" ? "desc" : "asc";
}

function parseYearParam(raw: string | null): number | null {
  if (raw === null || raw === "") return null;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1970 || parsed > 2100) {
    return null;
  }
  return parsed;
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
  const tagFilter = parseTagParam(searchParams.get("tag"));
  const libraryFilter = parseLibraryParam(searchParams.get("library"));
  const monitoredOnly = searchParams.get("monitoredOnly") === "true";
  const genreFilter = searchParams.get("genre") ?? "";
  const regionFilter = searchParams.get("region") ?? "";
  const yearFilter = parseYearParam(searchParams.get("year"));
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

  const setTagFilter = (next: TagFilterValue): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === ALL_TAGS) params.delete("tag");
        else params.set("tag", String(next));
        return params;
      },
      { replace: false },
    );
  };

  const setLibraryFilter = (next: LibraryFilterValue): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === ALL_LIBRARIES) params.delete("library");
        else params.set("library", String(next));
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

  const setGenreFilter = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        const trimmed = next.trim();
        if (trimmed === "") params.delete("genre");
        else params.set("genre", trimmed);
        return params;
      },
      { replace: false },
    );
  };

  const setRegionFilter = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        const trimmed = next.trim().toUpperCase();
        if (trimmed === "") params.delete("region");
        else params.set("region", trimmed);
        return params;
      },
      { replace: false },
    );
  };

  const setYearFilter = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "") {
          params.delete("year");
        } else {
          const parsed = Number.parseInt(next, 10);
          if (Number.isFinite(parsed) && parsed >= 1970 && parsed <= 2100) {
            params.set("year", String(parsed));
          } else {
            params.delete("year");
          }
        }
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
  const tags = useTags();
  const libraries = useLibraries();

  const params: ListGamesParams = useMemo(() => {
    const out: ListGamesParams = {
      limit: 200,
      sort: sortKey,
      direction: sortDirection,
    };
    if (urlQuery.length > 0) out.q = urlQuery;
    if (platformFilter !== ALL_PLATFORMS) out.platformId = platformFilter;
    if (tagFilter !== ALL_TAGS) out.tagId = tagFilter;
    if (libraryFilter !== ALL_LIBRARIES) out.libraryId = libraryFilter;
    if (monitoredOnly) out.monitored = true;
    if (genreFilter !== "") out.genre = genreFilter;
    if (regionFilter !== "") out.region = regionFilter;
    if (yearFilter !== null) out.year = yearFilter;
    return out;
  }, [
    urlQuery,
    platformFilter,
    tagFilter,
    libraryFilter,
    monitoredOnly,
    genreFilter,
    regionFilter,
    yearFilter,
    sortKey,
    sortDirection,
  ]);

  const games = useGames(params);

  const filtersActive =
    urlQuery.length > 0 ||
    platformFilter !== ALL_PLATFORMS ||
    tagFilter !== ALL_TAGS ||
    libraryFilter !== ALL_LIBRARIES ||
    monitoredOnly ||
    genreFilter !== "" ||
    regionFilter !== "" ||
    yearFilter !== null;


  const resetFilters = (): void => {
    // Clear the local query input so the debounced URL writer
    // doesn't immediately re-set ``q`` from the stale state
    // value. Sort + direction are preserved — they're not
    // "filters" in the operator's mental model.
    setQuery("");
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.delete("q");
        params.delete("platform");
        params.delete("tag");
        params.delete("library");
        params.delete("monitoredOnly");
        params.delete("genre");
        params.delete("region");
        params.delete("year");
        return params;
      },
      { replace: false },
    );
  };

  // -- Bulk select state (slices 151, 153) ----------------------------------
  const pushToast = useToastStore((s) => s.push);
  const bulkMonitor = useBulkMonitorGames();
  const [selectionActive, setSelectionActive] = useState(false);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);

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

  const beginSelectionFromLongPress = (gameId: number): void => {
    // Enter selection mode and pre-select the held card. Spec
    // D ("long-press for multi-select on Library and Wanted").
    setSelectionActive(true);
    setSelectedIds(new Set([gameId]));
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

        {/* Filter bar laid out on exactly two rows on desktop:
            Row 1 — search (flex) + platform + sort + direction +
                    selection mode toggle.
            Row 2 — tag + library + genre + region + year +
                    monitored-only toggle + reset (when active).
            Each row is ``flex-wrap`` so it stays a single line
            on a normal-width window and degrades gracefully to
            2-3 wrapped lines on a narrow one — never the full
            one-control-per-line stack the old ``flex-col``
            breakpoint produced below 768 px. */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="block min-w-[12rem] flex-1">
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

          <label className="block w-56">
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
                "inline-flex items-center justify-center rounded-md bg-zinc-950 px-3",
                "text-zinc-200 ring-1 ring-inset ring-zinc-700 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {sortDirection === "asc" ? (
                <ArrowUp size={14} strokeWidth={2.2} aria-hidden="true" />
              ) : (
                <ArrowDown size={14} strokeWidth={2.2} aria-hidden="true" />
              )}
            </button>
          </div>

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
                : "bg-zinc-950 text-zinc-200 ring-zinc-700 hover:bg-zinc-900",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {selectionActive
              ? t("bulk.exitSelection")
              : t("bulk.enterSelection")}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="block min-w-[10rem] flex-1">
            <span className="sr-only">{t("filters.tag.label")}</span>
            <select
              value={tagFilter === ALL_TAGS ? "" : String(tagFilter)}
              onChange={(e) => {
                const v = e.target.value;
                setTagFilter(
                  v === "" ? ALL_TAGS : Number.parseInt(v, 10),
                );
              }}
              aria-label={t("filters.tag.label")}
              disabled={!tags.isSuccess}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              <option value="">{t("filters.tag.all")}</option>
              {tags.data?.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block min-w-[10rem] flex-1">
            <span className="sr-only">{t("filters.library.label")}</span>
            <select
              value={libraryFilter === ALL_LIBRARIES ? "" : String(libraryFilter)}
              onChange={(e) => {
                const v = e.target.value;
                setLibraryFilter(
                  v === "" ? ALL_LIBRARIES : Number.parseInt(v, 10),
                );
              }}
              aria-label={t("filters.library.label")}
              disabled={!libraries.isSuccess}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              <option value="">{t("filters.library.all")}</option>
              {libraries.data?.map((lib) => (
                <option key={lib.id} value={lib.id}>
                  {lib.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block w-32">
            <span className="sr-only">{t("filters.genre.label")}</span>
            <input
              type="text"
              defaultValue={genreFilter}
              onBlur={(e) => setGenreFilter(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setGenreFilter((e.target as HTMLInputElement).value);
                }
              }}
              placeholder={t("filters.genre.placeholder")}
              aria-label={t("filters.genre.label")}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>

          <label className="block w-24">
            <span className="sr-only">{t("filters.region.label")}</span>
            <input
              type="text"
              defaultValue={regionFilter}
              onBlur={(e) => setRegionFilter(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setRegionFilter((e.target as HTMLInputElement).value);
                }
              }}
              placeholder={t("filters.region.placeholder")}
              aria-label={t("filters.region.label")}
              maxLength={4}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm uppercase text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>

          <label className="block w-24">
            <span className="sr-only">{t("filters.year.label")}</span>
            <input
              type="number"
              defaultValue={yearFilter ?? ""}
              onBlur={(e) => setYearFilter(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setYearFilter((e.target as HTMLInputElement).value);
                }
              }}
              placeholder={t("filters.year.placeholder")}
              aria-label={t("filters.year.label")}
              min={1970}
              max={2100}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>

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

          {filtersActive && (
            <button
              type="button"
              onClick={resetFilters}
              aria-label={t("filters.reset.aria")}
              title={t("filters.reset.aria")}
              className="shrink-0 rounded-md border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-400 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {t("filters.reset.label")}
            </button>
          )}
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
                onClick={() => setTagOpen(true)}
                disabled={selectedIds.size === 0 || bulkMonitor.isPending}
                className="rounded-md bg-brand/30 px-2 py-1 text-[0.65rem] font-medium text-brand hover:bg-brand/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t("bulk.tag.label")}
              </button>
              <button
                type="button"
                onClick={() => setDeleteOpen(true)}
                disabled={selectedIds.size === 0 || bulkMonitor.isPending}
                className="rounded-md bg-red-600 px-2 py-1 text-[0.65rem] font-medium text-zinc-50 hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t("bulk.delete.label")}
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
        <VirtualGrid
          items={games.data}
          itemKey={(game) => game.id}
          ariaLabel={t("title")}
          renderItem={(game) => (
            <GameCard
              game={game}
              selectionActive={selectionActive}
              selected={selectedIds.has(game.id)}
              onToggleSelect={toggleSelect}
              onLongPress={beginSelectionFromLongPress}
            />
          )}
        />
      )}

      {deleteOpen && games.data && (
        <BulkDeleteModal
          games={games.data.filter((g) => selectedIds.has(g.id))}
          onClose={() => setDeleteOpen(false)}
          onSuccess={exitSelection}
        />
      )}

      {tagOpen && games.data && (
        <BulkTagModal
          games={games.data.filter((g) => selectedIds.has(g.id))}
          onClose={() => setTagOpen(false)}
          onSuccess={exitSelection}
        />
      )}

      {!selectionActive && (
        <LinkFAB
          to="/add"
          ariaLabel={t("fab.addAria")}
          icon="+"
          label={t("fab.add")}
        />
      )}
    </div>
  );
}
