/**
 * Live download queue (Activity > Queue tab).
 *
 * Polls /api/v3/queue every 5s until the WebSocket bridge
 * ships. Each row carries progress / state / ETA / size.
 * Per-row pause/resume/remove actions land in a follow-up
 * slice when the spec 005 DownloadClient.remove + add
 * helpers are wired (T045/T046 in spec 013).
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useQueue, type QueueEntry } from "@/lib/api/queries/queue";

const STATE_BADGE: Record<string, string> = {
  queued: "bg-zinc-700/40 text-zinc-200 ring-zinc-500/40",
  downloading: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
  paused: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  completed: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  stuck: "bg-red-700/30 text-red-200 ring-red-500/40",
  failed: "bg-red-700/30 text-red-200 ring-red-500/40",
  pending_retry: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
};

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h${(minutes % 60).toString().padStart(2, "0")}m`;
}

function QueueRow(props: { entry: QueueEntry }): ReactElement {
  const { entry } = props;
  const stateClass =
    STATE_BADGE[entry.state] ??
    "bg-zinc-800 text-zinc-300 ring-zinc-700";
  const progressPct = Math.round(Math.min(1, entry.progress) * 100);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs text-zinc-300">
            {entry.downloadClientNativeId}
          </p>
          <p className="text-[0.7rem] text-zinc-500">
            release #{entry.releaseId} · client #{entry.downloadClientId}
            {entry.attemptCount > 0 &&
              ` · attempt ${entry.attemptCount}`}
          </p>
        </div>
        <span
          className={[
            "shrink-0 rounded-full px-2 py-0.5 text-[0.65rem]",
            "font-medium ring-1 ring-inset",
            stateClass,
          ].join(" ")}
        >
          {entry.state}
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800"
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Download progress ${progressPct}%`}
        >
          <div
            className="h-full bg-brand transition-[width]"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <span className="font-mono text-[0.7rem] text-zinc-400">
          {progressPct}%
        </span>
      </div>

      <div className="mt-2 flex justify-between font-mono text-[0.65rem] text-zinc-500">
        <span>size {formatBytes(entry.sizeBytes)}</span>
        <span>eta {formatEta(entry.etaSeconds)}</span>
      </div>

      {entry.errorMsg && (
        <p className="mt-2 text-[0.7rem] text-red-300">
          {entry.errorMsg}
        </p>
      )}
    </li>
  );
}

export function QueueList(): ReactElement {
  const { data, isPending, isError, error } = useQueue({
    pageSize: 50,
    sortKey: "last_updated_at",
    sortDirection: "desc",
  });

  if (isPending) return <ListSkeleton rows={5} />;
  if (isError) {
    return (
      <EmptyState
        title="Couldn't load queue"
        description={error.message}
      />
    );
  }
  if (data.records.length === 0) {
    return (
      <EmptyState
        title="Queue is empty"
        description="No active downloads. Triggering a missing search will queue grabs here."
      />
    );
  }
  return (
    <ul className="space-y-2">
      {data.records.map((entry) => (
        <QueueRow key={entry.id} entry={entry} />
      ))}
    </ul>
  );
}
