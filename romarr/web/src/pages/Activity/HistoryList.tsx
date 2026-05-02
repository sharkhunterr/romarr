/**
 * Paginated history list (Activity > History tab).
 *
 * Reuses the same useHistory hook the Dashboard uses, but
 * with a larger page size and pagination controls so the
 * operator can scroll back through the full audit trail.
 *
 * The filter chips (eventType / successful) land in a
 * follow-up slice when the canonical filter URL state is
 * designed.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { useState, type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useHistory } from "@/lib/api/queries/system";

const PAGE_SIZE = 50;

const EVENT_LABEL: Record<string, string> = {
  import: "Imported",
  search: "Searched",
  job_run: "Task ran",
};

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

export function HistoryList(): ReactElement {
  const [page, setPage] = useState(1);
  const { data, isPending, isError, error } = useHistory({
    page,
    pageSize: PAGE_SIZE,
    sortKey: "date",
    sortDirection: "desc",
  });

  if (isPending) return <ListSkeleton rows={8} />;
  if (isError) {
    return (
      <EmptyState
        title="Couldn't load history"
        description={error.message}
      />
    );
  }
  if (data.records.length === 0 && page === 1) {
    return (
      <EmptyState
        title="No history yet"
        description="Imports, searches, and scheduled tasks land here as they happen."
      />
    );
  }

  const totalPages = Math.max(
    1,
    Math.ceil(data.totalRecords / PAGE_SIZE),
  );

  return (
    <div className="space-y-3">
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
              {event.successful ? "ok" : "failed"}
            </span>
          </li>
        ))}
      </ul>

      {totalPages > 1 && (
        <nav
          className="flex items-center justify-between text-xs text-zinc-400"
          aria-label="History pagination"
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
            ← Previous
          </button>
          <span className="font-mono">
            page {page} / {totalPages} · {data.totalRecords} events
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
            Next →
          </button>
        </nav>
      )}
    </div>
  );
}
