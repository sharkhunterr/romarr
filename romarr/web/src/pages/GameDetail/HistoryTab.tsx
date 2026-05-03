/**
 * GameDetail > History tab (slice 94).
 *
 * Filters the unified `/api/v3/history` feed to a single
 * game via the spec-013 router's new `gameId` query param.
 * Job-run rows (which carry no game_id) are excluded
 * server-side, so the feed is import + search only.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useHistory } from "@/lib/api/queries/system";

const PAGE_SIZE = 50;

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
  const history = useHistory({
    gameId: props.gameId,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
  });

  if (history.isPending) return <ListSkeleton rows={6} />;
  if (history.isError) {
    return (
      <EmptyState
        title={t("history.loadError")}
        description={history.error.message}
      />
    );
  }
  if (history.data.records.length === 0) {
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
      {overflow && (
        <p className="text-[0.7rem] text-zinc-500">
          {t("history.showingMost", { count: history.data.records.length })}
        </p>
      )}
    </div>
  );
}
