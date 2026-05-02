/**
 * System > Backups tab.
 *
 * Lists every backup file under Settings.backup_path (spec 013
 * slice 35). Manual-trigger button POSTs to the unified
 * Sonarr-compat command bus
 * (POST /api/v3/command {"name": "Backup"}); per-row delete
 * is admin-only and lives in a follow-up slice with the
 * destructive-confirm modal.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTriggerCommand } from "@/lib/api/queries/system";
import { useBackups } from "@/lib/api/queries/system-extras";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

export function BackupsTab(): ReactElement {
  const { data, isPending, isError, error, refetch } = useBackups();
  const trigger = useTriggerCommand();

  const fireBackup = (): void => {
    trigger.mutate(
      { name: "Backup" },
      {
        onSuccess: () => {
          // Give the runner a beat to write the file, then
          // refresh the list.
          setTimeout(() => {
            void refetch();
          }, 1500);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-400">
          Backups land under the configured backup directory.
        </p>
        <button
          type="button"
          onClick={fireBackup}
          disabled={trigger.isPending}
          className={[
            "rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900",
            "hover:bg-brand-300",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {trigger.isPending ? "Running…" : "Backup now"}
        </button>
      </div>

      {isPending ? (
        <ListSkeleton rows={4} />
      ) : isError ? (
        <EmptyState
          title="Couldn't load backups"
          description={error.message}
        />
      ) : data.length === 0 ? (
        <EmptyState
          title="No backups yet"
          description="Run the scheduled Backup job or click Backup now to create one."
        />
      ) : (
        <ul className="space-y-2">
          {data.map((file) => (
            <li
              key={file.filename}
              className={[
                "flex items-center justify-between rounded-md",
                "border border-zinc-800 bg-zinc-900/40 px-3 py-2",
              ].join(" ")}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-xs text-zinc-200">
                  {file.filename}
                </p>
                <p className="text-[0.7rem] text-zinc-500">
                  {formatDate(file.lastWriteTime)} ·{" "}
                  {formatBytes(file.size)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
