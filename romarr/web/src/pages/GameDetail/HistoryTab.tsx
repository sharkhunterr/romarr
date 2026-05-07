/**
 * GameDetail > History tab (slice 94; slice 115 added filter
 * chips; slice 120 pushes everything to the server).
 *
 * Filters the unified `/api/v3/history` feed to a single
 * game via the spec-013 router's `gameId` query param.
 * Job-run rows (which carry no game_id) are excluded
 * server-side, so the feed is import + search only.
 *
 * Filter state — `historyFilter` (event-type chip) and
 * `failuresOnly` (toggle) — round-trips through
 * `useHistory({ eventType, successful })` so totals + page
 * counts always reflect the active filter.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useHistory,
  type HistoryEventType,
} from "@/lib/api/queries/system";

const PAGE_SIZE = 50;

type HistoryFilter = "all" | "import" | "search";

const FILTER_VALUES: readonly HistoryFilter[] = [
  "all",
  "import",
  "search",
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

interface HistoryTabProps {
  gameId: number;
}

function formatDate(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString(locale);
}

export function HistoryTab(props: HistoryTabProps): ReactElement {
  const { t, i18n } = useTranslation("game");
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = parseFilterParam(searchParams.get("historyFilter"));
  const failuresOnly = searchParams.get("failuresOnly") === "true";
  const range = parseRangeParam(searchParams.get("range"));

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
  };

  const eventType: HistoryEventType | undefined =
    filter === "all" ? undefined : filter;

  const history = useHistory({
    gameId: props.gameId,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
    eventType,
    successful: failuresOnly ? false : undefined,
    since: rangeToSinceIso(range),
  });

  const filtersActive = filter !== "all" || failuresOnly || range !== "all";

  if (history.isPending) return <ListSkeleton rows={6} />;
  if (history.isError) {
    return (
      <EmptyState
        title={t("history.loadError")}
        description={history.error.message}
      />
    );
  }
  if (history.data.records.length === 0 && !filtersActive) {
    return (
      <EmptyState
        title={t("history.empty.title")}
        description={t("history.empty.body")}
      />
    );
  }

  const overflow = history.data.totalRecords > history.data.records.length;

  return (
    <div className="space-y-2">
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

      {history.data.records.length === 0 && filtersActive && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("history.filter.noMatches")}
        </p>
      )}

      <ul className="space-y-2">
        {history.data.records.map((event) => {
          const summary = (event as { summary?: string | null }).summary;
          const reason = (event as { reason?: string | null }).reason;
          // Search rows ship search_type as summary (manual /
          // rss / cutoff / missing / auto_added) so the label
          // says "Manual grab" when the operator launched it
          // from this very modal.
          const labelKey =
            event.eventType === "search" && summary
              ? `history.searchType.${summary}`
              : `history.eventLabel.${event.eventType}`;
          const eventLabel = t(labelKey, { defaultValue: event.eventType });
          const showSummary =
            event.eventType !== "search" && summary && summary.length > 0;
          return (
            <li
              key={`${event.eventType}-${event.id}`}
              className={[
                "flex items-start justify-between gap-3 rounded-md",
                "border border-zinc-800 bg-zinc-900/40 px-3 py-2",
                "text-sm",
              ].join(" ")}
            >
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="truncate text-zinc-100">
                  <span className="font-mono text-[0.65rem] uppercase tracking-wider text-zinc-500">
                    {eventLabel}
                  </span>
                  <span className="ml-2 text-zinc-300">
                    {event.releaseId
                      ? t("history.subjectRelease", { id: event.releaseId })
                      : t("history.subjectGame")}
                  </span>
                </p>
                {showSummary && (
                  <p className="truncate text-[0.7rem] text-zinc-300">
                    {summary}
                  </p>
                )}
                {reason && (
                  <p className="truncate text-[0.7rem] text-red-300">
                    {reason}
                  </p>
                )}
                <p className="text-[0.7rem] text-zinc-500">
                  {formatDate(event.date, i18n.language)}
                </p>
              </div>
              <span
                className={[
                  "shrink-0 rounded-full px-2 py-0.5",
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
          );
        })}
      </ul>
      {overflow && !filtersActive && (
        <p className="text-[0.7rem] text-zinc-500">
          {t("history.showingMost", { count: history.data.records.length })}
        </p>
      )}
    </div>
  );
}
