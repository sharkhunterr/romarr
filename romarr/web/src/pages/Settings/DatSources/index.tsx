/**
 * Settings > DAT Sources sub-page (T106 — slice 267).
 *
 * Read-only summary of the DAT cache grouped by source. Each
 * row carries the entry count, the count of platforms covered,
 * and the most-recent ingestion timestamp. Refresh / re-import
 * is driven by the Tasks > Scheduler ``dat-update`` runner;
 * this page is the read surface only.
 *
 * Strings resolve through ``settings:datSources.*``.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useDatSources } from "@/lib/api/queries/dat-sources";

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

export function DatSourcesPage(): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const sources = useDatSources();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("datSources.title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          {t("datSources.subtitle")}
        </p>
      </header>

      {sources.isLoading && <ListSkeleton rows={3} />}

      {sources.isError && (
        <EmptyState
          title={t("datSources.loadError")}
          description={sources.error.message}
        />
      )}

      {sources.isSuccess && sources.data.length === 0 && (
        <EmptyState
          title={t("datSources.empty.title")}
          description={t("datSources.empty.body")}
        />
      )}

      {sources.isSuccess && sources.data.length > 0 && (
        <table className="w-full overflow-hidden rounded-lg border border-zinc-800 text-sm">
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
            {sources.data.map((row) => (
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
      )}

      <p className="text-xs text-zinc-500">{t("datSources.refreshHint")}</p>
    </div>
  );
}
