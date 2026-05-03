/**
 * Bulk-tag modal for the Library (slice 154).
 *
 * Two-action picker: "Add" (union the picked tags into each
 * selected Game's tag list) or "Remove" (strip them from the
 * list). Tag list itself is loaded from the existing useTags
 * hook so the operator picks from already-defined tags — new
 * tags are created on Settings > Tags.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useBulkTagGames,
  type Game,
} from "@/lib/api/queries/games";
import { useTags } from "@/lib/api/queries/tags";
import { useToastStore } from "@/lib/store/toast";

interface BulkTagModalProps {
  /** Selected games (count is shown in the title). */
  games: readonly Game[];
  onClose: () => void;
  onSuccess: () => void;
}

type Action = "add" | "remove";

export function BulkTagModal(props: BulkTagModalProps): ReactElement {
  const { t } = useTranslation("library");
  const pushToast = useToastStore((s) => s.push);
  const tags = useTags();
  const tag = useBulkTagGames();
  const [action, setAction] = useState<Action>("add");
  const [pickedIds, setPickedIds] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );

  function togglePick(tagId: number): void {
    setPickedIds((prev) => {
      const next = new Set(prev);
      if (next.has(tagId)) next.delete(tagId);
      else next.add(tagId);
      return next;
    });
  }

  function commit(): void {
    if (pickedIds.size === 0) return;
    const ids = props.games.map((g) => g.id);
    tag.mutate(
      {
        gameIds: ids,
        tagIds: Array.from(pickedIds),
        action,
      },
      {
        onSuccess: (resp) => {
          pushToast({
            kind: "success",
            title:
              action === "add"
                ? t("bulk.tag.addSuccessTitle")
                : t("bulk.tag.removeSuccessTitle"),
            description: t("bulk.tag.successBody", {
              updated: resp.updated,
              missing: resp.missing.length,
            }),
          });
          props.onSuccess();
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("bulk.tag.errorTitle"),
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
      aria-label={t("bulk.tag.modalTitle", { count: props.games.length })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("bulk.tag.modalTitle", { count: props.games.length })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("bulk.tag.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <fieldset className="space-y-1">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("bulk.tag.actionLabel")}
            </legend>
            <div className="flex gap-1.5">
              <ActionButton
                value="add"
                active={action === "add"}
                onClick={() => setAction("add")}
                label={t("bulk.tag.addAction")}
              />
              <ActionButton
                value="remove"
                active={action === "remove"}
                onClick={() => setAction("remove")}
                label={t("bulk.tag.removeAction")}
              />
            </div>
          </fieldset>

          <div className="space-y-1">
            <p className="text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("bulk.tag.tagsLabel")}
            </p>
            {tags.isPending && (
              <p className="text-xs text-zinc-500">
                {t("bulk.tag.loadingTags")}
              </p>
            )}
            {tags.isError && (
              <p className="text-xs text-red-400">{tags.error.message}</p>
            )}
            {tags.isSuccess && tags.data.length === 0 && (
              <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[0.65rem] text-amber-400">
                {t("bulk.tag.noTags")}
              </p>
            )}
            {tags.isSuccess && tags.data.length > 0 && (
              <ul className="flex max-h-[40vh] flex-wrap gap-1.5 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950/40 p-2">
                {tags.data.map((tg) => {
                  const picked = pickedIds.has(tg.id);
                  return (
                    <li key={tg.id}>
                      <button
                        type="button"
                        onClick={() => togglePick(tg.id)}
                        aria-pressed={picked}
                        className={[
                          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.65rem] font-medium",
                          "ring-1 ring-inset",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                          picked
                            ? "ring-brand"
                            : "ring-zinc-700 hover:ring-zinc-500",
                        ].join(" ")}
                        style={{
                          backgroundColor: picked
                            ? `${tg.color}40`
                            : `${tg.color}10`,
                          color: tg.color,
                        }}
                      >
                        <span
                          aria-hidden="true"
                          className="block h-2 w-2 rounded-full"
                          style={{ backgroundColor: tg.color }}
                        />
                        {tg.label}
                        {picked && <span aria-hidden="true">✓</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={tag.isPending}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("bulk.tag.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={pickedIds.size === 0 || tag.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {tag.isPending
              ? t("bulk.tag.submitting")
              : action === "add"
                ? t("bulk.tag.addSubmit", { count: pickedIds.size })
                : t("bulk.tag.removeSubmit", { count: pickedIds.size })}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ActionButton(props: {
  value: Action;
  active: boolean;
  onClick: () => void;
  label: string;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={props.onClick}
      aria-pressed={props.active}
      className={[
        "flex-1 rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        props.active
          ? "bg-brand/20 text-brand ring-brand/40"
          : "bg-zinc-950 text-zinc-300 ring-zinc-700 hover:bg-zinc-800",
      ].join(" ")}
    >
      {props.label}
    </button>
  );
}
