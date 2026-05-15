/**
 * Scheduler-job row rendered inside the Queue list (slice 475).
 *
 * Same visual language as :class:`QueueRow` so a scan / metadata
 * refresh sits next to the qBit / SAB downloads instead of in
 * its own banner. The ``items_processed`` field comes back live
 * from /api/v3/system/tasks; ``output_summary`` (live-updated by
 * the runner) carries the per-bucket breakdown that surfaces as
 * the matched / unmatched / remaining chips.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useCancelTaskRun } from "@/lib/api/queries/system-extras";
import { useToastStore } from "@/lib/store/toast";

interface RunningJob {
  id: string;
  name: string;
  current_run_id?: number | null;
  current_run_items_processed?: number | null;
  // Operator-friendly live breakdown the runner stashes via the
  // mid-run progress helper — carries ``total_items``,
  // ``matched``, ``unmatched``, etc.
  current_run_summary?: Record<string, unknown> | null;
}

const STATE_BADGE =
  "shrink-0 rounded-full px-2 py-0.5 text-[0.65rem] font-medium ring-1 ring-inset bg-emerald-700/30 text-emerald-200 ring-emerald-500/40";

function _readNumber(obj: unknown, key: string): number | null {
  if (typeof obj !== "object" || obj === null) return null;
  const value = (obj as Record<string, unknown>)[key];
  return typeof value === "number" ? value : null;
}

export function TaskQueueRow({ job }: { job: RunningJob }): ReactElement {
  const { t } = useTranslation("activity");
  const pushToast = useToastStore((s) => s.push);
  const cancel = useCancelTaskRun();

  const summary = job.current_run_summary ?? null;
  const processed = job.current_run_items_processed ?? 0;
  const total = _readNumber(summary, "total_items");
  const matched = _readNumber(summary, "matched");
  const unmatched = _readNumber(summary, "unmatched");
  const skipped = _readNumber(summary, "skipped");

  const pct =
    total != null && total > 0
      ? Math.min(100, Math.round((processed / total) * 100))
      : null;
  const remaining = total != null ? Math.max(0, total - processed) : null;

  function onCancel(): void {
    if (job.current_run_id == null) return;
    cancel.mutate(
      { jobId: job.id, runId: job.current_run_id },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("activeTasks.cancelToast", { name: job.name }),
          }),
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("activeTasks.cancelErrorToast"),
            description: err.message,
          }),
      },
    );
  }

  return (
    <li className="relative overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-emerald-400"
            />
            <p className="truncate text-xs font-medium text-zinc-100">
              {job.name}
            </p>
          </div>
          <p className="text-[0.7rem] text-zinc-500">
            {t("activeTasks.taskKindHint")}
          </p>
        </div>
        <span className={STATE_BADGE}>{t("activeTasks.running")}</span>
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800"
          role="progressbar"
          aria-valuenow={pct ?? 0}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={[
              "h-full transition-[width]",
              pct === null ? "animate-pulse bg-emerald-700/40" : "bg-emerald-500",
            ].join(" ")}
            style={{ width: pct === null ? "100%" : `${pct}%` }}
          />
        </div>
        <span className="font-mono text-[0.7rem] text-zinc-400">
          {pct === null
            ? t("activeTasks.itemsProcessed", { count: processed })
            : `${pct}%`}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[0.6rem]">
        {total != null && (
          <span className="rounded bg-zinc-800/60 px-1.5 py-0.5 text-zinc-300">
            {t("activeTasks.chips.processed", {
              processed,
              total,
            })}
          </span>
        )}
        {matched != null && (
          <span className="rounded bg-emerald-700/25 px-1.5 py-0.5 text-emerald-200">
            {t("activeTasks.chips.matched", { count: matched })}
          </span>
        )}
        {unmatched != null && unmatched > 0 && (
          <span className="rounded bg-amber-700/25 px-1.5 py-0.5 text-amber-200">
            {t("activeTasks.chips.unmatched", { count: unmatched })}
          </span>
        )}
        {skipped != null && skipped > 0 && (
          <span className="rounded bg-zinc-700/40 px-1.5 py-0.5 text-zinc-400">
            {t("activeTasks.chips.skipped", { count: skipped })}
          </span>
        )}
        {remaining != null && (
          <span className="rounded bg-zinc-800/60 px-1.5 py-0.5 text-zinc-400">
            {t("activeTasks.chips.remaining", { count: remaining })}
          </span>
        )}
      </div>

      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={onCancel}
          disabled={cancel.isPending || job.current_run_id == null}
          className={[
            "rounded-md border border-red-900/50 px-2.5 py-1",
            "text-[0.65rem] font-medium text-red-400",
            "hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {t("activeTasks.cancel")}
        </button>
      </div>
    </li>
  );
}
