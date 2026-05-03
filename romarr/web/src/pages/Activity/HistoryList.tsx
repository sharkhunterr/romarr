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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

export function HistoryList(): ReactElement {
  const { t } = useTranslation("activity");
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = parseFilterParam(searchParams.get("historyFilter"));
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

  const eventType: HistoryEventType | undefined =
    filter === "all" ? undefined : filter;

  const { data, isPending, isError, error } = useHistory({
    page,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
    eventType,
  });

  if (isPending) return <ListSkeleton rows={8} />;
  if (isError) {
    return (
      <EmptyState
        title={t("history.loadError")}
        description={error.message}
      />
    );
  }
  if (data.records.length === 0 && page === 1 && filter === "all") {
    // Only short-circuit to the EmptyState when there's truly
    // nothing — when a chip is active and the server returned
    // zero rows we want to keep the chip strip visible so the
    // operator can switch back to All without leaving the page.
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

      {data.records.length === 0 && filter !== "all" && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("history.filter.noMatches")}
        </p>
      )}

      <ul className="space-y-2">
        {data.records.map((event) => (
          <li
            key={`${event.eventType}-${event.id}`}
            className={[
              "flex items-center justify-between rounded-md",
              "border border-zinc-800 bg-zinc-900/40 px-3 py-2",
              "text-sm",
            ].join(" ")}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-zinc-100">
                <span className="font-mono text-[0.65rem] uppercase tracking-wider text-zinc-500">
                  {t(`history.eventLabel.${event.eventType}`, {
                    defaultValue: event.eventType,
                  })}
                </span>
                <span className="ml-2 text-zinc-300">
                  {event.gameId
                    ? t("history.subjectGame", { id: event.gameId })
                    : event.releaseId
                      ? t("history.subjectRelease", { id: event.releaseId })
                      : t("history.subjectEvent", { id: event.id })}
                </span>
              </p>
              <p className="text-[0.7rem] text-zinc-500">
                {formatDate(event.date)}
              </p>
            </div>
            <span
              className={[
                "ml-3 shrink-0 rounded-full px-2 py-0.5",
                "text-[0.65rem] font-medium ring-1 ring-inset",
                event.successful
                  ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
                  : "bg-red-700/30 text-red-200 ring-red-500/40",
              ].join(" ")}
            >
              {event.successful
                ? t("history.statusOk")
                : t("history.statusFailed")}
            </span>
          </li>
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
