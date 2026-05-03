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

  const eventType: HistoryEventType | undefined =
    filter === "all" ? undefined : filter;

  const history = useHistory({
    gameId: props.gameId,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
    eventType,
    successful: failuresOnly ? false : undefined,
  });

  const filtersActive = filter !== "all" || failuresOnly;

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
        {history.data.records.map((event) => (
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
                  {event.releaseId
                    ? t("history.subjectRelease", { id: event.releaseId })
                    : t("history.subjectGame")}
                </span>
              </p>
              <p className="text-[0.7rem] text-zinc-500">
                {formatDate(event.date, i18n.language)}
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
      {overflow && !filtersActive && (
        <p className="text-[0.7rem] text-zinc-500">
          {t("history.showingMost", { count: history.data.records.length })}
        </p>
      )}
    </div>
  );
}
