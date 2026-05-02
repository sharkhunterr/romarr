/**
 * System > Tasks tab.
 *
 * Lists the spec 012 scheduled jobs with their cron / interval,
 * last-run status, and a manual-trigger button. Per-row pause
 * and edit-schedule UIs land with the dedicated task-editor
 * slice (P-SYS sub-slice).
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTriggerCommand } from "@/lib/api/queries/system";
import { useTasks, type Job } from "@/lib/api/queries/system-extras";

const STATUS_BADGE: Record<string, string> = {
  success: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  failed: "bg-red-700/30 text-red-200 ring-red-500/40",
  partial: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  cancelled: "bg-zinc-700/40 text-zinc-200 ring-zinc-500/40",
  running: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
};

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

function formatSchedule(job: Job): string {
  if (job.schedule_cron) return `cron: ${job.schedule_cron}`;
  if (job.schedule_interval_seconds) {
    const seconds = job.schedule_interval_seconds;
    if (seconds < 60) return `every ${seconds}s`;
    if (seconds < 3600) return `every ${Math.round(seconds / 60)}m`;
    return `every ${Math.round(seconds / 3600)}h`;
  }
  return "event-driven";
}

interface TaskRowProps {
  job: Job;
  onTrigger: (id: string) => void;
  busy: boolean;
}

function TaskRow(props: TaskRowProps): ReactElement {
  const { job, onTrigger, busy } = props;
  const statusClass =
    STATUS_BADGE[job.last_run_status ?? ""] ??
    "bg-zinc-800 text-zinc-300 ring-zinc-700";

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-zinc-100">
            {job.name}
          </p>
          <p className="font-mono text-[0.7rem] text-zinc-500">
            {job.id} · {formatSchedule(job)}
          </p>
        </div>
        {job.last_run_status && (
          <span
            className={[
              "shrink-0 rounded-full px-2 py-0.5 text-[0.65rem]",
              "font-medium ring-1 ring-inset",
              statusClass,
            ].join(" ")}
          >
            {job.last_run_status}
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between">
        <p className="text-[0.7rem] text-zinc-500">
          last: {formatDate(job.last_run_at)} · next:{" "}
          {formatDate(job.next_run_at)}
        </p>
        {job.enabled && (
          <button
            type="button"
            onClick={() => onTrigger(job.id)}
            disabled={busy}
            className={[
              "ml-3 shrink-0 rounded-md border border-zinc-700 px-2.5 py-1",
              "text-xs font-medium text-zinc-200 hover:bg-zinc-800",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {busy ? "Triggering…" : "Run now"}
          </button>
        )}
      </div>

      {job.last_error && (
        <p className="mt-2 truncate text-[0.7rem] text-red-300">
          {job.last_error}
        </p>
      )}
    </li>
  );
}

export function TasksTab(): ReactElement {
  const { data, isPending, isError, error } = useTasks();
  const trigger = useTriggerCommand();

  if (isPending) return <ListSkeleton rows={6} />;
  if (isError) {
    return (
      <EmptyState
        title="Couldn't load tasks"
        description={error.message}
      />
    );
  }
  if (data.length === 0) {
    return (
      <EmptyState
        title="No scheduled tasks"
        description="The seeder populates the factory-default jobs on first boot."
      />
    );
  }

  return (
    <ul className="space-y-2">
      {data.map((job) => (
        <TaskRow
          key={job.id}
          job={job}
          onTrigger={(id) => trigger.mutate({ name: id })}
          busy={trigger.isPending && trigger.variables?.name === job.id}
        />
      ))}
    </ul>
  );
}
