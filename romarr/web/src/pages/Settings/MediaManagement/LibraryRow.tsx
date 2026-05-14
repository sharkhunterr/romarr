/**
 * One row in the Media Management list (slice 92).
 *
 * Library audit view: name + path + lifecycle pill +
 * status dot + flag pills (platform sub-folders, hardlinks,
 * delete-after-import, keep-dump-history) + exporter
 * roster + double-confirm delete with force-detach option
 * (mirrors the Tags `tag_in_use` flow from slice 51).
 */

import { AlertTriangle, Check, Pencil } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteLibrary,
  type Library,
} from "@/lib/api/queries/libraries";
import { useTriggerCommand } from "@/lib/api/queries/system";

import { CreateLibraryModal } from "./CreateLibraryModal";

interface LibraryRowProps {
  library: Library;
}

const STATUS_DOT: Record<string, string> = {
  ok: "bg-brand",
  degraded: "bg-amber-500",
  missing: "bg-red-500",
  stalled: "bg-amber-500",
};

function Pill(props: { label: string; tone?: "muted" | "amber" | "brand" }): ReactElement {
  const tone =
    props.tone === "amber"
      ? "bg-amber-950/40 text-amber-400"
      : props.tone === "brand"
        ? "bg-brand/20 text-brand"
        : "bg-zinc-800 text-zinc-300";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider ${tone}`}
    >
      {props.label}
    </span>
  );
}

export function LibraryRow(props: LibraryRowProps): ReactElement {
  const { library } = props;
  const { t } = useTranslation("settings");
  const del = useDeleteLibrary();
  const scan = useTriggerCommand();
  const [confirming, setConfirming] = useState(false);
  const [needsForce, setNeedsForce] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const lifecycleLabel =
    t(`mediaManagement.lifecycle.${library.lifecycle_policy}`, {
      defaultValue: library.lifecycle_policy,
    });
  const statusKey = library.status;
  const statusLabel = t(`mediaManagement.status.${statusKey}`, {
    defaultValue: statusKey,
  });
  const dotClass = STATUS_DOT[statusKey] ?? "bg-zinc-600";

  function attemptDelete(force: boolean): void {
    del.mutate(
      { id: library.id, force },
      {
        onSuccess: () => {
          setConfirming(false);
          setNeedsForce(false);
        },
        onError: (err) => {
          if (err.errorCode === "library_has_releases") {
            setNeedsForce(true);
          }
        },
      },
    );
  }

  const exporters: string[] = [];
  if (library.exporter_romm_enabled)
    exporters.push(t("mediaManagement.exporters.romm"));
  if (library.exporter_esde_enabled)
    exporters.push(t("mediaManagement.exporters.esde"));
  if (library.exporter_pegasus_enabled)
    exporters.push(t("mediaManagement.exporters.pegasus"));
  if (library.exporter_launchbox_enabled)
    exporters.push(t("mediaManagement.exporters.launchbox"));

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="space-y-2">
        <div className="flex items-start gap-2">
          <span
            aria-hidden="true"
            className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${dotClass}`}
          />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate text-sm font-medium text-zinc-100">
                {library.name}
              </p>
              <Pill label={lifecycleLabel} tone="brand" />
              <Pill label={statusLabel} />
            </div>
            <p className="truncate font-mono text-xs text-zinc-500">
              {library.path}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
          {library.platform_subfolders && (
            <span className="inline-flex items-center gap-1 rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              <Check size={10} aria-hidden="true" />
              {t("mediaManagement.platformSubfolders")}
            </span>
          )}
          {library.use_hardlinks && (
            <span className="inline-flex items-center gap-1 rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              <Check size={10} aria-hidden="true" />
              {t("mediaManagement.useHardlinks")}
            </span>
          )}
          {library.delete_after_import && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-950/40 px-1.5 py-0.5 text-amber-400">
              <AlertTriangle size={10} aria-hidden="true" />
              {t("mediaManagement.deleteAfterImport")}
            </span>
          )}
          {library.keep_dump_history && (
            <span className="inline-flex items-center gap-1 rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              <Check size={10} aria-hidden="true" />
              {t("mediaManagement.keepDumpHistory")}
            </span>
          )}
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
            {t("mediaManagement.minDiskFreeGb", { value: library.min_disk_free_gb })}
          </span>
        </div>

        {exporters.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
            <span className="text-zinc-500">
              {t("mediaManagement.exporters.label")}:
            </span>
            {exporters.map((label) => (
              <span
                key={label}
                className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-300"
              >
                {label}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() =>
            scan.mutate({ name: "RescanLibrary", libraryId: library.id })
          }
          disabled={scan.isPending}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
          title={
            scan.isError && scan.error?.message ? scan.error.message : undefined
          }
        >
          {scan.isPending
            ? t("mediaManagement.scan.pending")
            : scan.isSuccess && scan.variables?.libraryId === library.id
              ? t("mediaManagement.scan.queued")
              : t("mediaManagement.scan.button")}
        </button>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className={[
            "min-h-[36px] inline-flex items-center gap-1 rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          <Pencil size={12} aria-hidden="true" />
          {t("mediaManagement.edit.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {t("mediaManagement.delete.button")}
        </button>
      </div>

      {editOpen && (
        <CreateLibraryModal
          library={library}
          onClose={() => setEditOpen(false)}
        />
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("mediaManagement.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("mediaManagement.delete.confirmBody", { name: library.name })}
          </p>
          {needsForce && (
            <p className="mt-2 text-xs text-amber-300">
              {t("mediaManagement.delete.needsForce", { name: library.name })}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => attemptDelete(needsForce)}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {needsForce
                ? t("mediaManagement.delete.force")
                : t("mediaManagement.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
                setNeedsForce(false);
              }}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("mediaManagement.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
