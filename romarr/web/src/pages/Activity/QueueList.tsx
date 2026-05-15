/**
 * Live download queue (Activity > Queue tab).
 *
 * Polls /api/v3/queue every 5s until the WebSocket bridge
 * ships. Each row carries progress / state / ETA / size.
 * Per-row pause/resume/remove actions land in a follow-up
 * slice when the spec 005 DownloadClient.remove + add
 * helpers are wired (T045/T046 in spec 013).
 *
 * Strings resolve through `activity:queue.*` (slice 68).
 * The state pill itself is intentionally untranslated — the
 * documented enum values (`queued` / `downloading` / etc.)
 * are contract values, not operator copy.
 */

import { useEffect, useRef, useState, type ReactElement } from "react";
import { type TFunction } from "i18next";
import { useDrag } from "@use-gesture/react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useDownloadClientsById } from "@/lib/api/queries/download-clients";
import {
  useDeleteQueueEntry,
  useQueue,
  type QueueEntry,
  type QueueState,
} from "@/lib/api/queries/queue";
import { useActiveTasks } from "@/lib/api/queries/system-extras";

import { TaskQueueRow } from "./TaskQueueRow";

type StateFilter = "all" | QueueState;

const FILTER_VALUES: readonly StateFilter[] = [
  "all",
  "downloading",
  "queued",
  "paused",
  "stuck",
  "failed",
  "pending_retry",
];

const FILTER_SET: ReadonlySet<StateFilter> = new Set<StateFilter>(
  FILTER_VALUES,
);

function parseFilterParam(raw: string | null): StateFilter {
  return raw !== null && FILTER_SET.has(raw as StateFilter)
    ? (raw as StateFilter)
    : "all";
}

const STATE_BADGE: Record<string, string> = {
  queued: "bg-zinc-700/40 text-zinc-200 ring-zinc-500/40",
  downloading: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
  // Slice 467 — ROM-pack post-download phases.
  extracting: "bg-violet-700/30 text-violet-200 ring-violet-500/40",
  importing: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  paused: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  completed: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  stuck: "bg-red-700/30 text-red-200 ring-red-500/40",
  failed: "bg-red-700/30 text-red-200 ring-red-500/40",
  pending_retry: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
};

function formatBytes(bytes: number | null | undefined, t: TFunction): string {
  if (bytes === null || bytes === undefined) return t("queue.dash");
  if (bytes < 1024) return t("queue.bytes", { value: bytes });
  if (bytes < 1024 * 1024) {
    return t("queue.kilobytes", { value: Math.round(bytes / 1024) });
  }
  if (bytes < 1024 * 1024 * 1024) {
    return t("queue.megabytes", {
      value: (bytes / (1024 * 1024)).toFixed(1),
    });
  }
  return t("queue.gigabytes", {
    value: (bytes / (1024 * 1024 * 1024)).toFixed(2),
  });
}

function formatEta(seconds: number | null | undefined, t: TFunction): string {
  if (seconds === null || seconds === undefined) return t("queue.dash");
  if (seconds < 60) return t("queue.etaSeconds", { value: seconds });
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return t("queue.etaMinutes", { value: minutes });
  const hours = Math.floor(minutes / 60);
  return t("queue.etaHoursMinutes", {
    hours,
    minutes: (minutes % 60).toString().padStart(2, "0"),
  });
}

// Distance (px) the row must travel left before release fires
// the remove. Below the threshold the row springs back.
const SWIPE_THRESHOLD_PX = 100;

/** Two-sample velocity estimator — derives a live ETA from how
 * fast ``progress`` is climbing between successive poll ticks.
 * Falls back to the backend-supplied ``etaSeconds`` when the
 * download client already gave us one (qBit / SAB). */
function useProgressEta(
  progress: number,
  lastUpdatedAt: unknown,
): number | null {
  const sampleRef = useRef<{ progress: number; ts: number } | null>(null);
  const [eta, setEta] = useState<number | null>(null);
  useEffect(() => {
    const tsRaw =
      typeof lastUpdatedAt === "string" || typeof lastUpdatedAt === "number"
        ? new Date(lastUpdatedAt).getTime()
        : Number.NaN;
    const ts = Number.isFinite(tsRaw) ? tsRaw : Date.now();
    const prev = sampleRef.current;
    sampleRef.current = { progress, ts };
    if (
      prev !== null &&
      progress > prev.progress &&
      ts > prev.ts &&
      progress < 1
    ) {
      const dt = (ts - prev.ts) / 1000;
      const rate = (progress - prev.progress) / dt;
      if (rate > 0) {
        setEta(Math.round((1 - progress) / rate));
      }
    } else if (progress >= 1) {
      setEta(null);
    }
  }, [progress, lastUpdatedAt]);
  return eta;
}


function QueueRow(props: {
  entry: QueueEntry;
  clientName: string | null;
}): ReactElement {
  const { t } = useTranslation("activity");
  const { entry, clientName } = props;
  const remove = useDeleteQueueEntry();
  const stateClass =
    STATE_BADGE[entry.state] ??
    "bg-zinc-800 text-zinc-300 ring-zinc-700";
  const progressPct = Math.round(Math.min(1, entry.progress) * 100);
  // Backend-supplied ETA wins (qBit / SAB give us a real one);
  // for romarr-internal pack rows we derive one from progress
  // velocity so the operator sees a live, moving estimate.
  const estimatedEta = useProgressEta(entry.progress, entry.lastUpdatedAt);
  const displayedEta = entry.etaSeconds ?? estimatedEta;
  // Hide the "client #N" line for romarr-internal rows (URL
  // pack streams — slice 465) where there is no download client.
  const showClientLine =
    clientName !== null || entry.downloadClientId !== null;

  // Swipe-to-remove (T092 / spec 014 P-ACT). Touch-only — mouse
  // users hit the explicit Remove button instead. Drag the row
  // left past SWIPE_THRESHOLD_PX and release → fires the same
  // mutation the button does.
  const [swipeOffset, setSwipeOffset] = useState(0);
  const swipeBind = useDrag(
    ({ down, movement: [mx], last }) => {
      if (remove.isPending) {
        return;
      }
      // Right-direction swipes are no-ops; only left-swipe
      // (negative mx) triggers the remove gesture.
      const clamped = Math.min(0, Math.max(mx, -160));
      if (down) {
        setSwipeOffset(clamped);
        return;
      }
      if (last) {
        if (clamped <= -SWIPE_THRESHOLD_PX) {
          setSwipeOffset(0);
          remove.mutate({ id: entry.id, removeFromClient: true });
        } else {
          setSwipeOffset(0);
        }
      }
    },
    {
      axis: "x",
      filterTaps: true,
      pointer: { touch: true },
    },
  );

  function onRemove(): void {
    if (
      typeof window !== "undefined" &&
      !window.confirm(t("queue.removeConfirm"))
    ) {
      return;
    }
    remove.mutate({ id: entry.id, removeFromClient: true });
  }

  return (
    <li
      {...swipeBind()}
      data-swipe={swipeOffset < 0 ? "active" : "idle"}
      className="relative overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/40 p-3 touch-pan-y"
      style={{
        transform: `translateX(${swipeOffset}px)`,
        transition: swipeOffset === 0 ? "transform 200ms ease" : "none",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Slice 367: prefer the operator-readable torrent
              title and the parent game's name; fall back to
              the bare native id (info-hash) only when neither
              is on the row. */}
          <p className="truncate text-xs font-medium text-zinc-100">
            {entry.title ?? entry.downloadClientNativeId}
          </p>
          {entry.gameTitle && (
            <p className="truncate text-[0.7rem] text-zinc-300">
              {entry.gameTitle}
            </p>
          )}
          {(showClientLine || entry.attemptCount > 0) && (
            <p className="text-[0.7rem] text-zinc-500">
              {showClientLine &&
                (clientName ?? `client #${entry.downloadClientId}`)}
              {entry.attemptCount > 0 &&
                t("queue.attempt", { count: entry.attemptCount })}
            </p>
          )}
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
          aria-label={t("queue.progressLabel", { pct: progressPct })}
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
        <span>{t("queue.size", { value: formatBytes(entry.sizeBytes, t) })}</span>
        <span>{t("queue.eta", { value: formatEta(displayedEta, t) })}</span>
      </div>

      {entry.errorMsg && (
        <p className="mt-2 text-[0.7rem] text-red-300">
          {entry.errorMsg}
        </p>
      )}

      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={onRemove}
          disabled={remove.isPending}
          className={[
            "rounded-md border border-red-900/50 px-2.5 py-1",
            "text-[0.65rem] font-medium text-red-400",
            "hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
          aria-label={t("queue.removeAria", {
            id: entry.downloadClientNativeId,
          })}
        >
          {remove.isPending ? t("queue.removing") : t("queue.remove")}
        </button>
      </div>
      {remove.isError && (
        <p role="alert" className="mt-1 text-right text-[0.65rem] text-red-300">
          {remove.error?.message ?? t("queue.removeFailedFallback")}
        </p>
      )}
    </li>
  );
}

export function QueueList(): ReactElement {
  const { t } = useTranslation("activity");
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = parseFilterParam(searchParams.get("queueState"));
  const clientsById = useDownloadClientsById();
  // Scheduler jobs in flight (scan / metadata refresh / …)
  // render as queue rows at the top of the list. The hook
  // self-paces — polls 3 s while anything is running, off
  // otherwise (slice 475).
  const activeTasks = useActiveTasks();
  const running = (activeTasks.data ?? []).filter(
    (j) => j.current_run_id != null,
  );

  const setFilter = (next: StateFilter): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "all") params.delete("queueState");
        else params.set("queueState", next);
        return params;
      },
      { replace: false },
    );
  };

  const state: QueueState | undefined =
    filter === "all" ? undefined : filter;

  const { data, isPending, isError, error } = useQueue({
    pageSize: 50,
    sortKey: "last_updated_at",
    sortDirection: "desc",
    state,
  });

  if (isPending) return <ListSkeleton rows={5} />;
  if (isError) {
    return (
      <EmptyState
        title={t("queue.loadError")}
        description={error.message}
      />
    );
  }
  // Hide the empty-state when a scheduler task is in flight —
  // the operator IS looking at "something in progress".
  if (
    data.records.length === 0 &&
    filter === "all" &&
    running.length === 0
  ) {
    return (
      <EmptyState
        title={t("queue.empty.title")}
        description={t("queue.empty.body")}
      />
    );
  }
  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label={t("queue.filter.ariaLabel")}
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
            {t(`queue.filter.${value}`)}
          </button>
        ))}
      </div>

      {data.records.length === 0 && filter !== "all" && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("queue.filter.noMatches")}
        </p>
      )}

      <ul className="space-y-2">
        {/* Scheduler tasks first — visually consistent with the
            queue rows below so the operator scans the whole
            list as "stuff in progress". Slice 475. */}
        {running.map((job) => (
          <TaskQueueRow
            key={`task:${job.id}`}
            job={job as unknown as Parameters<typeof TaskQueueRow>[0]["job"]}
          />
        ))}
        {data.records.map((entry) => (
          <QueueRow
            key={entry.id}
            entry={entry}
            clientName={
              entry.downloadClientId == null
                ? null
                : clientsById.get(entry.downloadClientId)?.name ?? null
            }
          />
        ))}
      </ul>
    </div>
  );
}
