/**
 * Per-game pending-downloads banner (slice 109).
 *
 * Polls `/api/v3/queue?gameId=...` every 5s. Renders a thin
 * banner above the tab bar when any row exists; links to
 * /activity for the operator to drill in. Hides itself when
 * there's nothing pending so unread state never adds visual
 * noise to the overview.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useQueue } from "@/lib/api/queries/queue";

interface PendingDownloadsProps {
  gameId: number;
}

export function PendingDownloads(
  props: PendingDownloadsProps,
): ReactElement | null {
  const { t } = useTranslation("game");
  const queue = useQueue({
    gameId: props.gameId,
    pageSize: 50,
    sortKey: "last_updated_at",
    sortDirection: "desc",
  });

  const records = queue.data?.records ?? [];
  if (records.length === 0) return null;

  // Aggregate progress: average across active downloads. The
  // banner is informational; if the operator wants per-row
  // detail they click through to /activity.
  const avgProgress =
    records.reduce((sum, r) => sum + (r.progress ?? 0), 0) / records.length;

  return (
    <div
      className={[
        "mb-3 flex items-center gap-3 rounded-md border",
        "border-sky-900/50 bg-sky-950/20 px-3 py-2",
      ].join(" ")}
    >
      <span aria-hidden="true" className="text-base">
        ⬇️
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-sky-200">
          {t("pendingDownloads.title", { count: records.length })}
        </p>
        <p className="text-[0.65rem] text-zinc-400">
          {t("pendingDownloads.progress", {
            percent: Math.round(avgProgress * 100),
          })}
        </p>
      </div>
      <Link
        to="/activity"
        className={[
          "rounded-md border border-sky-800 px-2.5 py-1",
          "text-[0.7rem] font-medium text-sky-200",
          "hover:bg-sky-950/40",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
        ].join(" ")}
      >
        {t("pendingDownloads.openActivity")}
      </Link>
    </div>
  );
}
