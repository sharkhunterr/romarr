/**
 * Active-tasks banner (slice 473).
 *
 * Surfaces every scheduler job in flight (``current_run_id``
 * non-null) above the Activity tab list, so an operator who
 * just fired a scan / metadata refresh from the Library page
 * sees the task progressing rather than wondering whether
 * anything happened. Polls every 3 s while at least one job is
 * running; auto-collapses to nothing once everything settles.
 *
 * The Cancel button signals cooperative cancellation through
 * /api/v3/system/tasks/{jobId}/runs/{runId}/cancel; the runner
 * checks the registry at its next checkpoint.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useActiveTasks,
  useCancelTaskRun,
} from "@/lib/api/queries/system-extras";
import { useToastStore } from "@/lib/store/toast";

export function ActiveTasksBanner(): ReactElement | null {
  const { t } = useTranslation("activity");
  const pushToast = useToastStore((s) => s.push);
  const tasks = useActiveTasks();
  const cancel = useCancelTaskRun();

  const running = (tasks.data ?? []).filter(
    (j) => j.current_run_id != null,
  );
  if (running.length === 0) return null;

  function onCancel(jobId: string, runId: number, name: string): void {
    cancel.mutate(
      { jobId, runId },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("activeTasks.cancelToast", { name }),
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
    <section
      aria-label={t("activeTasks.ariaLabel")}
      className="mb-4 space-y-1.5 rounded-md border border-brand/40 bg-brand/5 p-3"
    >
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-brand">
        {t("activeTasks.heading", { count: running.length })}
      </p>
      <ul className="space-y-1.5">
        {running.map((job) => (
          <li
            key={job.id}
            className="flex items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950/40 px-3 py-2"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-brand"
              />
              <p className="truncate text-xs font-medium text-zinc-100">
                {job.name}
              </p>
              <span className="shrink-0 text-[0.6rem] uppercase tracking-wide text-zinc-500">
                {t("activeTasks.running")}
              </span>
              {(() => {
                // ``current_run_items_processed`` is a new
                // computed field (slice 474) — schema.ts will
                // pick it up on the next codegen pass; cast to
                // keep the build green in the meantime.
                const processed = (
                  job as unknown as {
                    current_run_items_processed?: number | null;
                  }
                ).current_run_items_processed;
                if (processed == null || processed <= 0) return null;
                return (
                  <span className="shrink-0 font-mono text-[0.6rem] text-zinc-400">
                    {t("activeTasks.itemsProcessed", { count: processed })}
                  </span>
                );
              })()}
            </div>
            {job.current_run_id != null && (
              <button
                type="button"
                onClick={() =>
                  onCancel(job.id, job.current_run_id!, job.name)
                }
                disabled={cancel.isPending}
                className="shrink-0 rounded border border-rose-700/50 px-2 py-1 text-[0.65rem] font-medium text-rose-200 hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t("activeTasks.cancel")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
