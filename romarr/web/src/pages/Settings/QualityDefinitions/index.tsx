/**
 * Settings > Quality Definitions sub-page (T106 — slice 266).
 *
 * Read-only summary surface: each platform's recognised formats
 * with their ``min_size_bytes`` / ``max_size_bytes`` floor + ceiling.
 * Editing flows through the existing per-platform format CRUD
 * under ``/api/v3/rom/platform/{id}/format/*`` (admin scope) —
 * exposed via the Platforms sub-page.
 *
 * Strings resolve through ``settings:qualityDefinitions.*``.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useQualityDefinitions,
  type QualityDefinitionFormat,
} from "@/lib/api/queries/quality-definitions";

const _MB = 1024 * 1024;

function _formatSize(bytes: number | null, t: (k: string) => string): string {
  if (bytes === null) return t("qualityDefinitions.unbounded");
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < _MB) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * _MB) return `${(bytes / _MB).toFixed(1)} MB`;
  return `${(bytes / (1024 * _MB)).toFixed(2)} GB`;
}

interface FormatRowProps {
  format: QualityDefinitionFormat;
}

function FormatRow(props: FormatRowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { format } = props;

  return (
    <tr className="border-t border-zinc-800">
      <td className="px-3 py-2 font-mono text-zinc-100">
        {format.extension}
      </td>
      <td className="px-3 py-2 text-zinc-300">{format.format_type}</td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
        {_formatSize(format.min_size_bytes, t)}
      </td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
        {_formatSize(format.max_size_bytes, t)}
      </td>
      <td className="px-3 py-2 text-xs">
        <span
          className={[
            "rounded-md px-2 py-0.5",
            format.pack_source === "builtin"
              ? "bg-zinc-800 text-zinc-300"
              : "bg-emerald-700/30 text-emerald-200",
          ].join(" ")}
        >
          {format.pack_source}
        </span>
      </td>
    </tr>
  );
}

export function QualityDefinitionsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const platforms = useQualityDefinitions();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("qualityDefinitions.title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          {t("qualityDefinitions.subtitle")}
        </p>
      </header>

      {platforms.isLoading && <ListSkeleton rows={4} />}

      {platforms.isError && (
        <EmptyState
          title={t("qualityDefinitions.loadError")}
          description={platforms.error.message}
        />
      )}

      {platforms.isSuccess && platforms.data.length === 0 && (
        <EmptyState
          title={t("qualityDefinitions.empty.title")}
          description={t("qualityDefinitions.empty.body")}
        />
      )}

      {platforms.isSuccess &&
        platforms.data.map((platform) => (
          <section
            key={platform.platform_id}
            aria-labelledby={`platform-${platform.platform_id}-h`}
            className="rounded-lg border border-zinc-800 bg-zinc-900/40"
          >
            <header className="flex items-baseline justify-between px-4 py-3">
              <h2
                id={`platform-${platform.platform_id}-h`}
                className="text-sm font-medium text-zinc-100"
              >
                {platform.platform_name}
              </h2>
              <span className="font-mono text-[0.65rem] text-zinc-500">
                {platform.platform_slug}
              </span>
            </header>
            {platform.formats.length === 0 ? (
              <p className="px-4 pb-4 text-xs text-zinc-500">
                {t("qualityDefinitions.platformNoFormats")}
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/60 text-left text-[0.65rem] uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-3 py-2">
                      {t("qualityDefinitions.cols.extension")}
                    </th>
                    <th className="px-3 py-2">
                      {t("qualityDefinitions.cols.formatType")}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t("qualityDefinitions.cols.minSize")}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t("qualityDefinitions.cols.maxSize")}
                    </th>
                    <th className="px-3 py-2">
                      {t("qualityDefinitions.cols.source")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {platform.formats.map((format) => (
                    <FormatRow key={format.id} format={format} />
                  ))}
                </tbody>
              </table>
            )}
          </section>
        ))}
    </div>
  );
}
