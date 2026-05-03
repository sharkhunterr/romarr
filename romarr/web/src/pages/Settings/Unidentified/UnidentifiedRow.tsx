/**
 * Single unidentified-dump row (slice 87).
 *
 * Shows filename + path + rejection_reason + size + attempt
 * count. Two actions: Match… (opens MatchModal) + Delete
 * (with double-confirm, drops the row but preserves the file
 * on disk per FR-038).
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteUnidentified,
  type UnidentifiedDump,
} from "@/lib/api/queries/unidentified";

import { MatchModal } from "./MatchModal";

interface UnidentifiedRowProps {
  unidentified: UnidentifiedDump;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function UnidentifiedRow(props: UnidentifiedRowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { unidentified } = props;
  const del = useDeleteUnidentified();
  const [confirming, setConfirming] = useState(false);
  const [matching, setMatching] = useState(false);

  const filename = useMemo(() => {
    const path = unidentified.path;
    const idx = path.lastIndexOf("/");
    return idx >= 0 ? path.slice(idx + 1) : path;
  }, [unidentified.path]);

  function confirmDelete(): void {
    del.mutate(unidentified.id, {
      onSuccess: () => setConfirming(false),
    });
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="truncate text-sm font-medium text-zinc-100">
            {filename}
          </p>
          <p className="truncate font-mono text-[0.65rem] text-zinc-500">
            {unidentified.path}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
            {unidentified.rejection_reason && (
              <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-amber-400">
                {t("unidentified.rejection.label")}:{" "}
                {unidentified.rejection_reason}
              </span>
            )}
            <span className="rounded bg-zinc-800 px-1.5 py-0.5">
              {t("unidentified.size", {
                value: formatBytes(unidentified.size_bytes),
              })}
            </span>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5">
              {t("unidentified.attempts", {
                count: unidentified.attempt_count,
              })}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setMatching(true)}
          className={[
            "min-h-[36px] rounded-md bg-brand px-3 text-xs font-medium text-zinc-900",
            "hover:bg-brand-300",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {t("unidentified.actions.match")}
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
          {t("unidentified.actions.delete")}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("unidentified.actions.deleteConfirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("unidentified.actions.deleteConfirmBody")}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("unidentified.actions.deleteConfirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("unidentified.actions.deleteCancel")}
            </button>
          </div>
        </div>
      )}

      {matching && (
        <MatchModal
          unidentified={unidentified}
          onClose={() => setMatching(false)}
        />
      )}
    </li>
  );
}
