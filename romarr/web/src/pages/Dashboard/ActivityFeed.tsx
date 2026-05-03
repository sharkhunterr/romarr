/**
 * Recent activity feed (T062 part 3, T118).
 *
 * Pulls the unified history (UNION across import_history /
 * search_history / job_run from spec 013 T058) sorted by date
 * descending, capped at 10 rows for the dashboard. The full
 * paginated history view lives on the Activity page (P-ACT).
 *
 * Slice 170 / T118: timestamps are now formatted via the
 * locale-aware ``formatRelativeTime`` helper so the feed reads
 * "il y a 2 minutes" in FR mode instead of always falling back
 * to the OS locale.
 *
 * Strings resolve through `dashboard:activity.*` (slice 67).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useHistory } from "@/lib/api/queries/system";
import { formatRelativeTime } from "@/lib/i18n/dates";

export function ActivityFeed(): ReactElement {
  const { t, i18n } = useTranslation("dashboard");
  const { data, isPending, isError, error } = useHistory({
    pageSize: 10,
    sortKey: "date",
    sortDirection: "desc",
  });

  if (isPending) {
    return <ListSkeleton rows={5} />;
  }

  if (isError) {
    return (
      <EmptyState
        title={t("activity.loadError")}
        description={error?.message}
      />
    );
  }

  if (data.records.length === 0) {
    return (
      <EmptyState
        title={t("activity.empty.title")}
        description={t("activity.empty.body")}
      />
    );
  }

  return (
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
                {t(`activity.eventLabel.${event.eventType}`, {
                  defaultValue: event.eventType,
                })}
              </span>
              <span className="ml-2 text-zinc-300">
                {event.gameId
                  ? t("activity.subjectGame", { id: event.gameId })
                  : event.releaseId
                    ? t("activity.subjectRelease", { id: event.releaseId })
                    : t("activity.subjectEvent", { id: event.id })}
              </span>
            </p>
            <p className="text-[0.7rem] text-zinc-500">
              {formatRelativeTime(event.date, i18n.resolvedLanguage)}
            </p>
          </div>
          <span
            className={[
              "ml-3 shrink-0 rounded-full px-2 py-0.5 text-[0.65rem] font-medium ring-1 ring-inset",
              event.successful
                ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
                : "bg-red-700/30 text-red-200 ring-red-500/40",
            ].join(" ")}
          >
            {event.successful ? t("activity.statusOk") : t("activity.statusFailed")}
          </span>
        </li>
      ))}
    </ul>
  );
}
