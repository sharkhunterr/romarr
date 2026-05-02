/**
 * System > Backups tab.
 *
 * Lists every backup file under Settings.backup_path (spec 013
 * slice 35). Manual-trigger button POSTs to the unified
 * Sonarr-compat command bus
 * (POST /api/v3/command {"name": "Backup"}); per-row delete
 * is admin-only and lives in a follow-up slice with the
 * destructive-confirm modal.
 *
 * Strings resolve through `system:backups.*` (slice 69).
 */

import { type ReactElement } from "react";
import { type TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTriggerCommand } from "@/lib/api/queries/system";
import { useBackups } from "@/lib/api/queries/system-extras";

function formatBytes(bytes: number, t: TFunction): string {
  if (bytes < 1024) return t("backups.bytes", { value: bytes });
  if (bytes < 1024 * 1024) {
    return t("backups.kilobytes", { value: Math.round(bytes / 1024) });
  }
  if (bytes < 1024 * 1024 * 1024) {
    return t("backups.megabytes", {
      value: (bytes / (1024 * 1024)).toFixed(1),
    });
  }
  return t("backups.gigabytes", {
    value: (bytes / (1024 * 1024 * 1024)).toFixed(2),
  });
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

export function BackupsTab(): ReactElement {
  const { t } = useTranslation("system");
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
        <p className="text-xs text-zinc-400">{t("backups.intro")}</p>
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
          {trigger.isPending ? t("backups.running") : t("backups.trigger")}
        </button>
      </div>

      {isPending ? (
        <ListSkeleton rows={4} />
      ) : isError ? (
        <EmptyState
          title={t("backups.loadError")}
          description={error.message}
        />
      ) : data.length === 0 ? (
        <EmptyState
          title={t("backups.empty.title")}
          description={t("backups.empty.body")}
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
                  {formatBytes(file.size, t)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
