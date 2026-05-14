/**
 * Settings > DAT Sources sub-page (slices 267 + 444).
 *
 * Two stacked surfaces:
 * - Aggregated cache summary (legacy contract — rows by
 *   authority name) showing how many entries / platforms are
 *   currently loaded.
 * - Per-row CRUD table for the ``dat_source`` rows the operator
 *   has configured. Each row exposes Edit / Delete / Refresh
 *   buttons; the header offers Add and Refresh-all.
 *
 * Strings resolve through ``settings:datSources.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useDatSources,
  useDatSourceRows,
  useDeleteDatSource,
  useRefreshAllDatSources,
  useRefreshDatSource,
  type DatRefreshStatus,
  type DatSourceRead,
} from "@/lib/api/queries/dat-sources";
import { useToastStore } from "@/lib/store/toast";

import { CreateDatSourceModal } from "./CreateDatSourceModal";

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

function _statusBadge(
  status: DatRefreshStatus | null,
  t: ReturnType<typeof useTranslation<"settings">>["t"],
): ReactElement {
  if (status === null) {
    return (
      <span className="rounded bg-zinc-700/40 px-1.5 py-0.5 text-[0.65rem] text-zinc-400">
        {t("datSources.status.never")}
      </span>
    );
  }
  const cls =
    status === "ok"
      ? "bg-emerald-700/30 text-emerald-200"
      : status === "failed"
        ? "bg-rose-700/30 text-rose-200"
        : "bg-amber-700/30 text-amber-200";
  const key =
    status === "ok" ? "ok" : status === "failed" ? "failed" : "running";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[0.65rem] ${cls}`}>
      {t(`datSources.status.${key}`)}
    </span>
  );
}

export function DatSourcesPage(): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const summary = useDatSources();
  const rows = useDatSourceRows();
  const del = useDeleteDatSource();
  const refresh = useRefreshDatSource();
  const refreshAll = useRefreshAllDatSources();
  const pushToast = useToastStore((s) => s.push);

  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<DatSourceRead | null>(null);
  const [refreshingId, setRefreshingId] = useState<number | null>(null);

  function onDelete(row: DatSourceRead): void {
    if (!window.confirm(t("datSources.deleteConfirm", { name: row.name }))) {
      return;
    }
    del.mutate(row.id, {
      onSuccess: () =>
        pushToast({ kind: "success", title: t("datSources.deletedToast") }),
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("datSources.deleteErrorToast"),
          description: err.message,
        }),
    });
  }

  function onRefresh(row: DatSourceRead): void {
    setRefreshingId(row.id);
    refresh.mutate(row.id, {
      onSuccess: (outcome) => {
        setRefreshingId(null);
        if (outcome.status === "ok") {
          pushToast({
            kind: "success",
            title: t("datSources.refreshDoneToast", {
              name: outcome.name,
              count: outcome.entries_ingested ?? 0,
            }),
          });
        } else {
          pushToast({
            kind: "error",
            title: t("datSources.refreshFailedToast", {
              error: outcome.error ?? "unknown",
            }),
          });
        }
      },
      onError: (err) => {
        setRefreshingId(null);
        pushToast({
          kind: "error",
          title: t("datSources.refreshFailedToast", { error: err.message }),
        });
      },
    });
  }

  function onRefreshAll(): void {
    refreshAll.mutate(undefined, {
      onSuccess: (outcomes) => {
        const ok = outcomes.filter((o) => o.status === "ok").length;
        pushToast({
          kind: ok === outcomes.length ? "success" : "warning",
          title: t("datSources.refreshAllDoneToast", {
            ok,
            total: outcomes.length,
          }),
        });
      },
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("datSources.refreshAllErrorToast"),
          description: err.message,
        }),
    });
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("datSources.title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          {t("datSources.subtitle")}
        </p>
      </header>

      {/* ---- Aggregated cache summary ------------------------------ */}
      <section className="space-y-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">
            {t("datSources.summaryTitle")}
          </h2>
          <p className="text-xs text-zinc-500">{t("datSources.summaryHint")}</p>
        </div>

        {summary.isLoading && <ListSkeleton rows={3} />}

        {summary.isError && (
          <EmptyState
            title={t("datSources.loadError")}
            description={summary.error.message}
          />
        )}

        {summary.isSuccess && summary.data.length === 0 && (
          <EmptyState
            title={t("datSources.empty.title")}
            description={t("datSources.empty.body")}
          />
        )}

        {summary.isSuccess && summary.data.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full min-w-[32rem] text-sm">
            <thead className="bg-zinc-900/60 text-left text-[0.65rem] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2.5">{t("datSources.cols.source")}</th>
                <th className="px-4 py-2.5 text-right">
                  {t("datSources.cols.entries")}
                </th>
                <th className="px-4 py-2.5 text-right">
                  {t("datSources.cols.platforms")}
                </th>
                <th className="px-4 py-2.5 text-right">
                  {t("datSources.cols.latestUpdate")}
                </th>
              </tr>
            </thead>
            <tbody>
              {summary.data.map((row) => (
                <tr
                  key={row.source}
                  className="border-t border-zinc-800 hover:bg-zinc-900/40"
                >
                  <td className="px-4 py-2.5 font-medium text-zinc-100">
                    <span className="rounded-md bg-emerald-700/30 px-2 py-0.5 text-xs text-emerald-200">
                      {row.source}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-zinc-300">
                    {row.entry_count.toLocaleString(i18n.language)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-zinc-300">
                    {row.platform_count}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-zinc-400">
                    {_formatTimestamp(row.latest_updated_at, i18n.language)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {/* ---- Configured sources CRUD ------------------------------- */}
      <section className="space-y-2">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-200">
              {t("datSources.rowsTitle")}
            </h2>
            <p className="text-xs text-zinc-500">{t("datSources.rowsHint")}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRefreshAll}
              disabled={refreshAll.isPending || (rows.data?.length ?? 0) === 0}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {refreshAll.isPending
                ? t("datSources.refreshAllRunning")
                : t("datSources.refreshAllButton")}
            </button>
            <button
              type="button"
              onClick={() => setShowAdd(true)}
              className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {t("datSources.addButton")}
            </button>
          </div>
        </div>

        {rows.isLoading && <ListSkeleton rows={3} />}

        {rows.isError && (
          <EmptyState
            title={t("datSources.loadError")}
            description={rows.error.message}
          />
        )}

        {rows.isSuccess && rows.data.length === 0 && (
          <p className="rounded-md border border-dashed border-zinc-800 px-4 py-6 text-center text-xs text-zinc-500">
            {t("datSources.rowsEmpty")}
          </p>
        )}

        {rows.isSuccess && rows.data.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full min-w-[44rem] text-sm">
            <thead className="bg-zinc-900/60 text-left text-[0.65rem] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2.5">{t("datSources.cols.platform")}</th>
                <th className="px-3 py-2.5">{t("datSources.cols.source")}</th>
                <th className="px-3 py-2.5">{t("datSources.cols.name")}</th>
                <th className="px-3 py-2.5">{t("datSources.cols.status")}</th>
                <th className="px-3 py-2.5 text-right">
                  {t("datSources.cols.lastEntries")}
                </th>
                <th className="px-3 py-2.5 text-right">
                  {t("datSources.cols.latestUpdate")}
                </th>
                <th className="px-3 py-2.5 text-right">
                  {t("datSources.cols.actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((row) => (
                <tr
                  key={row.id}
                  className={`border-t border-zinc-800 hover:bg-zinc-900/40 ${row.enabled ? "" : "opacity-50"}`}
                >
                  <td className="px-3 py-2.5 text-xs text-zinc-300">
                    {row.platform_name ?? row.platform_slug ?? `#${row.platform_id}`}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="rounded bg-emerald-700/30 px-1.5 py-0.5 text-[0.65rem] text-emerald-200">
                      {row.source}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-zinc-100">
                    {row.name}
                  </td>
                  <td className="px-3 py-2.5">
                    {_statusBadge(row.last_refresh_status, t)}
                    {row.last_refresh_error !== null && (
                      <p className="mt-0.5 max-w-xs truncate font-mono text-[0.6rem] text-rose-300">
                        {row.last_refresh_error}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs text-zinc-300">
                    {row.last_entry_count !== null
                      ? row.last_entry_count.toLocaleString(i18n.language)
                      : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-[0.7rem] text-zinc-400">
                    {_formatTimestamp(row.last_refresh_at, i18n.language)}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => onRefresh(row)}
                        disabled={
                          refreshingId === row.id || refreshAll.isPending
                        }
                        className="rounded border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {refreshingId === row.id
                          ? t("datSources.action.refreshing")
                          : t("datSources.action.refresh")}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditing(row)}
                        className="rounded border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800"
                      >
                        {t("datSources.action.edit")}
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(row)}
                        disabled={del.isPending}
                        className="rounded border border-rose-700/50 px-2 py-1 text-[0.65rem] font-medium text-rose-200 hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {t("datSources.action.delete")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {showAdd && (
        <CreateDatSourceModal onClose={() => setShowAdd(false)} />
      )}
      {editing !== null && (
        <CreateDatSourceModal
          editing={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
