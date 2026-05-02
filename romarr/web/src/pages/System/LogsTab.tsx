/**
 * System > Logs tab.
 *
 * Lists every log file Romarr has rotated under
 * Settings.log_dir (spec 013 slice 34). Each file links to
 * the admin-only download endpoint
 * /api/v3/system/log/file/{filename}; the cookie session
 * carries auth.
 *
 * Strings resolve through `system:logs.*` (slice 69).
 */

import { type ReactElement } from "react";
import { type TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useLogFiles } from "@/lib/api/queries/system-extras";

function formatBytes(bytes: number, t: TFunction): string {
  if (bytes < 1024) return t("logs.bytes", { value: bytes });
  if (bytes < 1024 * 1024) {
    return t("logs.kilobytes", { value: Math.round(bytes / 1024) });
  }
  return t("logs.megabytes", { value: (bytes / (1024 * 1024)).toFixed(1) });
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString();
}

export function LogsTab(): ReactElement {
  const { t } = useTranslation("system");
  const { data, isPending, isError, error } = useLogFiles();

  if (isPending) return <ListSkeleton rows={5} />;
  if (isError) {
    return (
      <EmptyState
        title={t("logs.loadError")}
        description={error.message}
      />
    );
  }
  if (data.length === 0) {
    return (
      <EmptyState
        title={t("logs.empty.title")}
        description={t("logs.empty.body")}
      />
    );
  }
  return (
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
              {formatBytes(file.contentsSize, t)}
            </p>
          </div>
          <a
            href={`/api/v3/system/log/file/${encodeURIComponent(file.filename)}`}
            target="_blank"
            rel="noreferrer"
            className={[
              "ml-3 shrink-0 rounded-md border border-zinc-700",
              "px-2.5 py-1 text-xs font-medium text-zinc-200",
              "hover:bg-zinc-800",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          >
            {t("logs.download")}
          </a>
        </li>
      ))}
    </ul>
  );
}
