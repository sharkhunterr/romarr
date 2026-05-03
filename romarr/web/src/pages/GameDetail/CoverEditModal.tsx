/**
 * Cover override modal (slice 160).
 *
 * Two operator workflows:
 *   * Paste a URL → backend fetches the bytes, persists them
 *     into ``<data_dir>/covers/``, and locks the ``cover``
 *     field so the next refresh doesn't overwrite the pick.
 *   * Reset → DELETE the current cover; the aggregator will
 *     refetch on the next refresh unless the field is locked
 *     (the modal mentions this in the body copy).
 *
 * Strings resolve through the ``game`` namespace.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteGameCover,
  useSetGameCover,
  type Game,
} from "@/lib/api/queries/games";
import { useToastStore } from "@/lib/store/toast";

interface CoverEditModalProps {
  game: Game;
  onClose: () => void;
}

export function CoverEditModal(props: CoverEditModalProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const setCover = useSetGameCover();
  const removeCover = useDeleteGameCover();
  const [url, setUrl] = useState("");

  const submitting = setCover.isPending || removeCover.isPending;

  function commit(): void {
    const trimmed = url.trim();
    if (trimmed.length === 0) return;
    setCover.mutate(
      { gameId: props.game.id, url: trimmed },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("overview.cover.successTitle"),
            description: t("overview.cover.successBody"),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("overview.cover.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  function reset(): void {
    removeCover.mutate(
      { gameId: props.game.id },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("overview.cover.resetSuccessTitle"),
            description: t("overview.cover.resetSuccessBody"),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("overview.cover.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("overview.cover.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("overview.cover.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("overview.cover.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("overview.cover.urlLabel")}
            </span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit();
                if (e.key === "Escape") props.onClose();
              }}
              placeholder={t("overview.cover.urlPlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[0.65rem] text-zinc-500">
            {t("overview.cover.autoLockHint")}
          </p>

          {props.game.cover_path && (
            <button
              type="button"
              onClick={reset}
              disabled={submitting}
              className="w-full rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {removeCover.isPending
                ? t("overview.cover.resetting")
                : t("overview.cover.reset")}
            </button>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("overview.cover.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={url.trim().length === 0 || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {setCover.isPending
              ? t("overview.cover.saving")
              : t("overview.cover.save")}
          </button>
        </footer>
      </div>
    </div>
  );
}
