/**
 * Settings > Content Packs sub-page (slice 461).
 *
 * A ROM content pack is a downloadable archive holding many
 * ROMs (a No-Intro full set, an archive.org romset, a curated
 * bundle). The operator registers a pack here, hits Ingest, and
 * the backend streams → extracts → DAT-matches → imports every
 * ROM in one pass.
 *
 * The table polls itself while any pack is mid-ingest so the
 * status badge + progress bar advance live. Packs that finish
 * with unmatched ROMs land in ``awaiting_triage`` — the triage
 * modal (slice 462) resolves those per-file.
 *
 * Strings resolve through ``settings:romPacks.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  ROM_PACK_BUSY_STATUSES,
  useDeleteRomPack,
  useIngestRomPack,
  useRomPacks,
  type RomPackRead,
  type RomPackStatus,
} from "@/lib/api/queries/rom-packs";
import { useToastStore } from "@/lib/store/toast";

import { CreateRomPackModal } from "./CreateRomPackModal";
import { PackDetailModal } from "./PackDetailModal";

const _GIB = 1024 ** 3;
const _MIB = 1024 ** 2;
const _KIB = 1024;

function _formatBytes(bytes: number | null): string {
  if (bytes === null || bytes <= 0) return "—";
  if (bytes >= _GIB) return `${(bytes / _GIB).toFixed(1)} GiB`;
  if (bytes >= _MIB) return `${(bytes / _MIB).toFixed(1)} MiB`;
  if (bytes >= _KIB) return `${(bytes / _KIB).toFixed(0)} KiB`;
  return `${bytes} B`;
}

function _formatTimestamp(iso: string | null, locale: string): string {
  if (iso === null) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "—";
  return d.toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Status → badge colour. */
function _statusClass(status: RomPackStatus): string {
  switch (status) {
    case "done":
      return "bg-emerald-700/30 text-emerald-200";
    case "failed":
      return "bg-rose-700/30 text-rose-200";
    case "awaiting_triage":
      return "bg-amber-700/30 text-amber-200";
    case "pending":
      return "bg-zinc-700/40 text-zinc-300";
    default:
      // downloading / extracting / importing — work in progress
      return "bg-sky-700/30 text-sky-200";
  }
}

function _statusBadge(
  status: RomPackStatus,
  t: ReturnType<typeof useTranslation<"settings">>["t"],
): ReactElement {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[0.65rem] ${_statusClass(status)}`}
    >
      {t(`romPacks.status.${status}`)}
    </span>
  );
}

/** Imported / total progress bar, shown once a pack has files. */
function _progress(row: RomPackRead): ReactElement | null {
  if (row.total_files === 0) return null;
  const done =
    row.imported_count +
    row.unmatched_count +
    row.parked_count +
    row.failed_count;
  const pct = Math.min(100, Math.round((done / row.total_files) * 100));
  return (
    <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-zinc-800">
      <div
        className="h-full rounded-full bg-brand transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function RomPacksPage(): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const packs = useRomPacks();
  const del = useDeleteRomPack();
  const ingest = useIngestRomPack();
  const pushToast = useToastStore((s) => s.push);

  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<RomPackRead | null>(null);
  const [detailPack, setDetailPack] = useState<RomPackRead | null>(null);
  const [ingestingId, setIngestingId] = useState<number | null>(null);

  function onDelete(row: RomPackRead): void {
    if (!window.confirm(t("romPacks.deleteConfirm", { name: row.name }))) {
      return;
    }
    del.mutate(row.id, {
      onSuccess: () =>
        pushToast({ kind: "success", title: t("romPacks.deletedToast") }),
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("romPacks.deleteErrorToast"),
          description: err.message,
        }),
    });
  }

  function onIngest(row: RomPackRead): void {
    setIngestingId(row.id);
    ingest.mutate(row.id, {
      onSuccess: () => {
        setIngestingId(null);
        pushToast({
          kind: "success",
          title: t("romPacks.ingestStartedToast", { name: row.name }),
        });
      },
      onError: (err) => {
        setIngestingId(null);
        pushToast({
          kind: "error",
          title: t("romPacks.ingestErrorToast"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("romPacks.title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t("romPacks.subtitle")}</p>
      </header>

      <section className="space-y-2">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-200">
              {t("romPacks.rowsTitle")}
            </h2>
            <p className="text-xs text-zinc-500">{t("romPacks.rowsHint")}</p>
          </div>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("romPacks.addButton")}
          </button>
        </div>

        {packs.isLoading && <ListSkeleton rows={3} />}

        {packs.isError && (
          <EmptyState
            title={t("romPacks.loadError")}
            description={packs.error.message}
          />
        )}

        {packs.isSuccess && packs.data.length === 0 && (
          <EmptyState
            title={t("romPacks.empty.title")}
            description={t("romPacks.empty.body")}
          />
        )}

        {packs.isSuccess && packs.data.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full min-w-[52rem] text-sm">
              <thead className="bg-zinc-900/60 text-left text-[0.65rem] uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-3 py-2.5">{t("romPacks.cols.name")}</th>
                  <th className="px-3 py-2.5">
                    {t("romPacks.cols.platform")}
                  </th>
                  <th className="px-3 py-2.5">{t("romPacks.cols.status")}</th>
                  <th className="px-3 py-2.5">
                    {t("romPacks.cols.results")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("romPacks.cols.size")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("romPacks.cols.lastIngest")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("romPacks.cols.actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {packs.data.map((row) => {
                  const busy = ROM_PACK_BUSY_STATUSES.has(row.status);
                  return (
                    <tr
                      key={row.id}
                      className="border-t border-zinc-800 align-top hover:bg-zinc-900/40"
                    >
                      <td className="px-3 py-2.5">
                        <button
                          type="button"
                          onClick={() => setDetailPack(row)}
                          className="text-left text-xs font-medium text-zinc-100 hover:text-brand focus-visible:outline-none focus-visible:underline"
                        >
                          {row.name}
                        </button>
                        {row.url !== null && (
                          <p className="max-w-xs truncate font-mono text-[0.6rem] text-zinc-500">
                            {row.url}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-zinc-300">
                        {row.platform_name ??
                          row.platform_slug ??
                          t("romPacks.platformAny")}
                      </td>
                      <td className="px-3 py-2.5">
                        {_statusBadge(row.status, t)}
                        {_progress(row)}
                        {row.last_error !== null && (
                          <p className="mt-0.5 max-w-xs truncate font-mono text-[0.6rem] text-rose-300">
                            {row.last_error}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        {row.total_files === 0 ? (
                          <span className="text-xs text-zinc-600">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1 text-[0.6rem]">
                            <span className="rounded bg-emerald-700/25 px-1.5 py-0.5 text-emerald-200">
                              {t("romPacks.results.imported", {
                                count: row.imported_count,
                              })}
                            </span>
                            {row.unmatched_count > 0 && (
                              <span className="rounded bg-amber-700/25 px-1.5 py-0.5 text-amber-200">
                                {t("romPacks.results.unmatched", {
                                  count: row.unmatched_count,
                                })}
                              </span>
                            )}
                            {row.parked_count > 0 && (
                              <span className="rounded bg-zinc-700/40 px-1.5 py-0.5 text-zinc-300">
                                {t("romPacks.results.parked", {
                                  count: row.parked_count,
                                })}
                              </span>
                            )}
                            {row.failed_count > 0 && (
                              <span className="rounded bg-rose-700/25 px-1.5 py-0.5 text-rose-200">
                                {t("romPacks.results.failed", {
                                  count: row.failed_count,
                                })}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-zinc-300">
                        {_formatBytes(row.size_bytes)}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[0.7rem] text-zinc-400">
                        {_formatTimestamp(row.last_ingest_at, i18n.language)}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center justify-end gap-1">
                          {row.status === "awaiting_triage" && (
                            <button
                              type="button"
                              onClick={() => setDetailPack(row)}
                              className="rounded border border-amber-600/60 bg-amber-700/20 px-2 py-1 text-[0.65rem] font-medium text-amber-200 hover:bg-amber-700/30"
                            >
                              {t("romPacks.action.triage", {
                                count: row.unmatched_count,
                              })}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => onIngest(row)}
                            disabled={busy || ingestingId === row.id}
                            className="rounded border border-brand/60 px-2 py-1 text-[0.65rem] font-medium text-brand hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {busy
                              ? t("romPacks.action.running")
                              : row.status === "pending"
                                ? t("romPacks.action.ingest")
                                : t("romPacks.action.reIngest")}
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditing(row)}
                            disabled={busy}
                            className="rounded border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {t("romPacks.action.edit")}
                          </button>
                          <button
                            type="button"
                            onClick={() => onDelete(row)}
                            disabled={busy || del.isPending}
                            className="rounded border border-rose-700/50 px-2 py-1 text-[0.65rem] font-medium text-rose-200 hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {t("romPacks.action.delete")}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showAdd && <CreateRomPackModal onClose={() => setShowAdd(false)} />}
      {editing !== null && (
        <CreateRomPackModal
          editing={editing}
          onClose={() => setEditing(null)}
        />
      )}
      {detailPack !== null && (
        <PackDetailModal
          pack={detailPack}
          onClose={() => setDetailPack(null)}
        />
      )}
    </div>
  );
}
