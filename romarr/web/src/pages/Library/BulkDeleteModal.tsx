/**
 * Destructive confirm modal for the Library bulk-delete action
 * (slice 153).
 *
 * Per the constitution destructive actions are confirmed twice:
 *   * The modal itself acts as one confirm step.
 *   * The Delete button is held inactive for 1 second after
 *     mount so the operator can't muscle-memory through it.
 *
 * Files on disk are NEVER touched by this surface — that's the
 * per-library lifecycle policy's job. The modal copy makes
 * that distinction explicit so the operator isn't surprised.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useBulkDeleteGames,
  type Game,
} from "@/lib/api/queries/games";
import { useToastStore } from "@/lib/store/toast";

interface BulkDeleteModalProps {
  /** Selected games (for the title preview). */
  games: readonly Game[];
  onClose: () => void;
  onSuccess: () => void;
}

const ARM_DELAY_MS = 1_000;
const PREVIEW_LIMIT = 5;

export function BulkDeleteModal(
  props: BulkDeleteModalProps,
): ReactElement {
  const { t } = useTranslation("library");
  const pushToast = useToastStore((s) => s.push);
  const remove = useBulkDeleteGames();
  const [armed, setArmed] = useState(false);
  // Slice 469 — opt-in cascade to the on-disk ROM files.
  // Default off so the destructive surface stays conservative;
  // the operator explicitly ticks the box.
  const [deleteFiles, setDeleteFiles] = useState(false);

  // Spec: 1-second delay before the Delete button accepts a
  // click. The clock starts on mount, not on focus, so the
  // operator can read the modal copy first.
  useEffect(() => {
    const handle = window.setTimeout(() => setArmed(true), ARM_DELAY_MS);
    return () => window.clearTimeout(handle);
  }, []);

  function commit(): void {
    if (!armed) return;
    const ids = props.games.map((g) => g.id);
    remove.mutate(
      { gameIds: ids, deleteFiles },
      {
        onSuccess: (resp) => {
          pushToast({
            kind: "success",
            title: t("bulk.delete.successTitle"),
            description: t("bulk.delete.successBody", {
              deleted: resp.deleted,
              missing: resp.missing.length,
            }),
          });
          props.onSuccess();
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("bulk.delete.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  const previewTitles = props.games.slice(0, PREVIEW_LIMIT).map((g) => g.title);
  const overflowCount = Math.max(0, props.games.length - PREVIEW_LIMIT);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("bulk.delete.modalTitle", { count: props.games.length })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-red-700/50 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 bg-red-950/30 px-4 py-3">
          <h2 className="text-sm font-semibold text-red-200">
            {t("bulk.delete.modalTitle", { count: props.games.length })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-red-300/80">
            {t("bulk.delete.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <p className="text-xs text-zinc-300">
            {t("bulk.delete.body")}
          </p>
          {previewTitles.length > 0 && (
            <ul className="space-y-0.5 rounded-md border border-zinc-800 bg-zinc-950/40 p-2 text-[0.7rem] text-zinc-300">
              {previewTitles.map((title, idx) => (
                <li key={idx} className="truncate">
                  • {title}
                </li>
              ))}
              {overflowCount > 0 && (
                <li className="text-[0.65rem] text-zinc-500">
                  {t("bulk.delete.overflow", { count: overflowCount })}
                </li>
              )}
            </ul>
          )}
          <label
            className={[
              "flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2",
              deleteFiles
                ? "border-red-600/60 bg-red-950/30"
                : "border-amber-700/40 bg-amber-950/20",
            ].join(" ")}
          >
            <input
              type="checkbox"
              checked={deleteFiles}
              onChange={(e) => setDeleteFiles(e.target.checked)}
              disabled={remove.isPending}
              className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-zinc-700 bg-zinc-950 text-red-500 focus:ring-red-500"
            />
            <span
              className={[
                "text-[0.7rem]",
                deleteFiles ? "text-red-200" : "text-amber-300",
              ].join(" ")}
            >
              {deleteFiles
                ? t("bulk.delete.diskCascadeOn")
                : t("bulk.delete.diskCascadeOff")}
            </span>
          </label>
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={remove.isPending}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("bulk.delete.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!armed || remove.isPending}
            aria-disabled={!armed || remove.isPending}
            className={[
              "rounded-md px-3 py-1.5 text-xs font-medium",
              "bg-red-600 text-zinc-50 hover:bg-red-500",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {remove.isPending
              ? t("bulk.delete.deleting")
              : !armed
                ? t("bulk.delete.arming")
                : t("bulk.delete.confirm", { count: props.games.length })}
          </button>
        </footer>
      </div>
    </div>
  );
}
