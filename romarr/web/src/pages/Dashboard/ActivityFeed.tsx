/**
 * Recent activity feed (T062 part 3).
 *
 * Pulls the unified history (UNION across import_history /
 * search_history / job_run from spec 013 T058) sorted by date
 * descending, capped at 10 rows for the dashboard. The full
 * paginated history view lives on the Activity page (P-ACT).
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useHistory } from "@/lib/api/queries/system";

const EVENT_LABEL: Record<string, string> = {
  import: "Imported",
  search: "Searched",
  job_run: "Task ran",
};

function formatRelative(dateStr: string): string {
  // Lightweight relative-time formatter — date-fns would do
  // this with locale support, but date-fns is a follow-up
  // dep. For now we render the operator's local time format.
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) {
    return dateStr;
  }
  return date.toLocaleString();
}

export function ActivityFeed(): ReactElement {
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
        title="Couldn't load activity"
        description={error?.message}
      />
    );
  }

  if (data.records.length === 0) {
    return (
      <EmptyState
        title="No recent activity"
        description="Imports, searches, and scheduled tasks land here as they happen."
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
                {EVENT_LABEL[event.eventType] ?? event.eventType}
              </span>
              <span className="ml-2 text-zinc-300">
                {event.gameId
                  ? `game #${event.gameId}`
                  : event.releaseId
                    ? `release #${event.releaseId}`
                    : `event #${event.id}`}
              </span>
            </p>
            <p className="text-[0.7rem] text-zinc-500">
              {formatRelative(event.date)}
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
            {event.successful ? "ok" : "failed"}
          </span>
        </li>
      ))}
    </ul>
  );
}
