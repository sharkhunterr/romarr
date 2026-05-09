/**
 * Paginated history list (Activity > History tab).
 *
 * Reuses the same useHistory hook the Dashboard uses, but
 * with a larger page size and pagination controls so the
 * operator can scroll back through the full audit trail.
 *
 * Slice 116 adds client-side filter chips (All / Import /
 * Search / Job) that persist via the
 * `?historyFilter=import|search|job_run` query param —
 * mirrors the GameDetail history pattern from slice 115.
 *
 * Strings resolve through `activity:history.*` (slice 68).
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useHistory,
  type HistoryEventType,
} from "@/lib/api/queries/system";

import { HistoryRow } from "./HistoryRow";

const PAGE_SIZE = 50;

type HistoryFilter = "all" | "import" | "search" | "job_run";

const FILTER_VALUES: readonly HistoryFilter[] = [
  "all",
  "import",
  "search",
  "job_run",
];

const FILTER_SET: ReadonlySet<HistoryFilter> = new Set<HistoryFilter>(
  FILTER_VALUES,
);

function parseFilterParam(raw: string | null): HistoryFilter {
  return raw !== null && FILTER_SET.has(raw as HistoryFilter)
    ? (raw as HistoryFilter)
    : "all";
}

type TimeRange = "all" | "1h" | "24h" | "7d" | "30d";

const TIME_RANGE_VALUES: readonly TimeRange[] = [
  "all",
  "1h",
  "24h",
  "7d",
  "30d",
];

const TIME_RANGE_SET: ReadonlySet<TimeRange> = new Set<TimeRange>(
  TIME_RANGE_VALUES,
);

function parseRangeParam(raw: string | null): TimeRange {
  return raw !== null && TIME_RANGE_SET.has(raw as TimeRange)
    ? (raw as TimeRange)
    : "all";
}

function rangeToSinceIso(range: TimeRange): string | undefined {
  if (range === "all") return undefined;
  const now = Date.now();
  const ms = {
    "1h": 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  }[range];
  return new Date(now - ms).toISOString();
}

export function HistoryList(): ReactElement {
  const { t, i18n } = useTranslation("activity");
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = parseFilterParam(searchParams.get("historyFilter"));
  const failuresOnly = searchParams.get("failuresOnly") === "true";
  const range = parseRangeParam(searchParams.get("range"));
  const [page, setPage] = useState(1);

  const setFilter = (next: HistoryFilter): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "all") params.delete("historyFilter");
        else params.set("historyFilter", next);
        return params;
      },
      { replace: false },
    );
    setPage(1);
  };

  const setFailuresOnly = (next: boolean): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next) params.set("failuresOnly", "true");
        else params.delete("failuresOnly");
        return params;
      },
      { replace: false },
    );
    setPage(1);
  };

  const setRange = (next: TimeRange): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "all") params.delete("range");
        else params.set("range", next);
        return params;
      },
      { replace: false },
    );
    setPage(1);
  };

  const eventType: HistoryEventType | undefined =
    filter === "all" ? undefined : filter;

  const { data, isPending, isError, error } = useHistory({
    page,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
    eventType,
    successful: failuresOnly ? false : undefined,
    since: rangeToSinceIso(range),
  });

  const filtersActive = filter !== "all" || failuresOnly || range !== "all";

  if (isPending) return <ListSkeleton rows={8} />;
  if (isError) {
    return (
      <EmptyState
        title={t("history.loadError")}
        description={error.message}
      />
    );
  }
  if (data.records.length === 0 && page === 1 && !filtersActive) {
    // Only short-circuit to the EmptyState when there's truly
    // nothing — when a filter is active and the server returned
    // zero rows we want to keep the controls visible so the
    // operator can clear them without leaving the page.
    return (
      <EmptyState
        title={t("history.empty.title")}
        description={t("history.empty.body")}
      />
    );
  }

  const totalPages = Math.max(
    1,
    Math.ceil(data.totalRecords / PAGE_SIZE),
  );

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label={t("history.range.ariaLabel")}
        className="flex flex-wrap gap-1"
      >
        {TIME_RANGE_VALUES.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setRange(value)}
            aria-pressed={range === value}
            className={[
              "rounded-md px-3 py-1 text-xs font-medium ring-1 ring-inset",
              "transition-colors",
              range === value
                ? "bg-brand/20 text-brand ring-brand/40"
                : "bg-zinc-900/40 text-zinc-400 ring-zinc-700 hover:bg-zinc-800",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {t(`history.range.${value}`)}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div
          role="tablist"
          aria-label={t("history.filter.ariaLabel")}
          className="flex flex-wrap gap-1"
        >
          {FILTER_VALUES.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
              className={[
                "rounded-md px-3 py-1 text-xs font-medium ring-1 ring-inset",
                "transition-colors",
                filter === value
                  ? "bg-brand/20 text-brand ring-brand/40"
                  : "bg-zinc-900/40 text-zinc-400 ring-zinc-700 hover:bg-zinc-800",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t(`history.filter.${value}`)}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setFailuresOnly(!failuresOnly)}
          aria-pressed={failuresOnly}
          className={[
            "rounded-md px-3 py-1 text-xs font-medium ring-1 ring-inset",
            "transition-colors",
            failuresOnly
              ? "bg-red-700/30 text-red-200 ring-red-500/40"
              : "bg-zinc-900/40 text-zinc-400 ring-zinc-700 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {failuresOnly
            ? t("history.failuresOnly.on")
            : t("history.failuresOnly.off")}
        </button>
      </div>

      {data.records.length === 0 && filtersActive && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("history.filter.noMatches")}
        </p>
      )}

      <ul className="space-y-2">
        {data.records.map((event) => (
          <HistoryRow
            key={`${event.eventType}-${event.id}`}
            event={event}
            i18nNs="activity"
            locale={i18n.language}
          />
        ))}
      </ul>

      {totalPages > 1 && (
        <nav
          className="flex items-center justify-between text-xs text-zinc-400"
          aria-label={t("history.paginationAria")}
        >
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className={[
              "rounded-md border border-zinc-700 px-3 py-1",
              "hover:bg-zinc-800 disabled:cursor-not-allowed",
              "disabled:opacity-50",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          >
            {t("history.previous")}
          </button>
          <span className="font-mono">
            {t("history.pagination", {
              page,
              total: totalPages,
              count: data.totalRecords,
            })}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() =>
              setPage((p) => Math.min(totalPages, p + 1))
            }
            className={[
              "rounded-md border border-zinc-700 px-3 py-1",
              "hover:bg-zinc-800 disabled:cursor-not-allowed",
              "disabled:opacity-50",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          >
            {t("history.next")}
          </button>
        </nav>
      )}
    </div>
  );
}
