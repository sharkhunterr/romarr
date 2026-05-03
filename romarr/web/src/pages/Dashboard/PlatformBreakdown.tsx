/**
 * Per-platform breakdown panel (slice 105).
 *
 * Reads `byPlatform` from `useSystemStats()` and renders one
 * row per platform with games / releases / dumps / disk usage.
 * The panel is collapsed below 4 entries and lazily expands;
 * for now we just render the full list — the operator will
 * tell us when 50+ platforms hit the spec.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useSystemStats } from "@/lib/api/queries/system";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KiB", "MiB", "GiB", "TiB"];
  const i = Math.min(
    sizes.length - 1,
    Math.floor(Math.log(bytes) / Math.log(k)),
  );
  return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 2)} ${sizes[i]}`;
}

export function PlatformBreakdown(): ReactElement | null {
  const { t } = useTranslation("dashboard");
  const stats = useSystemStats();
  const rows = stats.data?.byPlatform ?? [];

  if (!stats.isSuccess) return null;
  if (rows.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/40">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-800 text-[0.65rem] uppercase tracking-wider text-zinc-500">
            <th className="px-3 py-2 font-medium">
              {t("platforms.platform")}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t("platforms.games")}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t("platforms.releases")}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t("platforms.dumps")}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t("platforms.disk")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.platformId}
              className="border-b border-zinc-800 last:border-b-0 text-zinc-200"
            >
              <td className="px-3 py-2 font-medium">{row.platformName}</td>
              <td className="px-3 py-2 text-right font-mono">
                {row.totalGames}
              </td>
              <td className="px-3 py-2 text-right font-mono">
                {row.totalReleases}
              </td>
              <td className="px-3 py-2 text-right font-mono">
                {row.totalDumps}
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-300">
                {formatBytes(row.totalSizeBytes)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
