/**
 * Single tag row with inline edit + delete.
 *
 * Click "Edit" to swap the static label / color into editable
 * inputs; "Save" runs `useUpdateTag`; "Delete" runs
 * `useDeleteTag`. The 409 "tag_in_use" path prompts the
 * operator to confirm a force-delete.
 *
 * Strings resolve through `settings:tags.row.*` (slice 66).
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  useDeleteTag,
  useUpdateTag,
  type Tag,
} from "@/lib/api/queries/tags";

export interface TagRowProps {
  tag: Tag;
}

export function TagRow(props: TagRowProps): ReactElement {
  const { tag } = props;
  const { t } = useTranslation("settings");
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(tag.label);
  const [color, setColor] = useState(tag.color);

  const update = useUpdateTag();
  const remove = useDeleteTag();

  const onSave = (): void => {
    update.mutate(
      { id: tag.id, payload: { label, color } },
      { onSuccess: () => setEditing(false) },
    );
  };

  const onCancel = (): void => {
    setLabel(tag.label);
    setColor(tag.color);
    setEditing(false);
  };

  const onDelete = (): void => {
    remove.mutate({ id: tag.id });
  };

  const onForceDelete = (): void => {
    if (
      window.confirm(t("tags.row.forcePrompt", { label: tag.label }))
    ) {
      remove.mutate({ id: tag.id, force: true });
    }
  };

  // The destructive-action path follows the spec 013 contract:
  // first DELETE returns 409 with errorCode "tag_in_use" when
  // assignments exist; the UI surfaces a force-delete button.
  const inUse = remove.error?.errorCode === "tag_in_use";

  return (
    <li
      className={[
        "rounded-md border border-zinc-800 bg-zinc-900/40 p-3",
        "space-y-2",
      ].join(" ")}
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="inline-block h-4 w-4 shrink-0 rounded"
          style={{ backgroundColor: editing ? color : tag.color }}
        />
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                aria-label={t("tags.create.label")}
                className={[
                  "rounded-md bg-zinc-950 px-2 py-1 text-sm text-zinc-100",
                  "ring-1 ring-inset ring-zinc-700",
                  "focus-visible:outline-none focus-visible:ring-2",
                  "focus-visible:ring-brand",
                ].join(" ")}
              />
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                aria-label={t("tags.create.color")}
                className={[
                  "h-8 w-12 rounded-md bg-zinc-950",
                  "ring-1 ring-inset ring-zinc-700",
                ].join(" ")}
              />
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate text-sm font-medium text-zinc-100">
                  {tag.label}
                </p>
                <span
                  className={[
                    "rounded-full px-1.5 py-0.5 font-mono text-[0.6rem]",
                    "uppercase tracking-wider ring-1 ring-inset",
                    tag.usageCount > 0
                      ? "bg-brand/20 text-brand ring-brand/40"
                      : "bg-zinc-800 text-zinc-500 ring-zinc-700",
                  ].join(" ")}
                  title={t("tags.row.usageTooltip", { count: tag.usageCount })}
                >
                  {t("tags.row.usageCount", { count: tag.usageCount })}
                </span>
              </div>
              <p className="font-mono text-[0.7rem] text-zinc-500">
                {tag.name} · {tag.color}
              </p>
            </>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {editing ? (
            <>
              <button
                type="button"
                onClick={onSave}
                disabled={update.isPending}
                className={[
                  "rounded-md bg-brand px-2 py-1 text-xs font-medium text-zinc-900",
                  "hover:bg-brand-300 disabled:opacity-60",
                  "focus-visible:outline-none focus-visible:ring-2",
                  "focus-visible:ring-brand",
                ].join(" ")}
              >
                {update.isPending ? t("tags.row.saving") : t("tags.row.save")}
              </button>
              <button
                type="button"
                onClick={onCancel}
                className={[
                  "rounded-md border border-zinc-700 px-2 py-1",
                  "text-xs font-medium text-zinc-200 hover:bg-zinc-800",
                  "focus-visible:outline-none focus-visible:ring-2",
                  "focus-visible:ring-brand",
                ].join(" ")}
              >
                {t("tags.row.cancel")}
              </button>
            </>
          ) : (
            <>
              {tag.usageCount > 0 && (
                <Link
                  to={`/library?tag=${tag.id}`}
                  aria-label={t("tags.row.viewGamesAria", {
                    count: tag.usageCount,
                    label: tag.label,
                  })}
                  title={t("tags.row.viewGames", {
                    count: tag.usageCount,
                  })}
                  className={[
                    "rounded-md border border-zinc-700 px-2 py-1",
                    "text-xs font-medium text-brand hover:bg-zinc-800",
                    "focus-visible:outline-none focus-visible:ring-2",
                    "focus-visible:ring-brand",
                  ].join(" ")}
                >
                  →
                </Link>
              )}
              <button
                type="button"
                onClick={() => setEditing(true)}
                className={[
                  "rounded-md border border-zinc-700 px-2 py-1",
                  "text-xs font-medium text-zinc-200 hover:bg-zinc-800",
                  "focus-visible:outline-none focus-visible:ring-2",
                  "focus-visible:ring-brand",
                ].join(" ")}
              >
                {t("tags.row.edit")}
              </button>
              {inUse ? (
                <button
                  type="button"
                  onClick={onForceDelete}
                  disabled={remove.isPending}
                  className={[
                    "rounded-md border border-red-700 px-2 py-1",
                    "text-xs font-medium text-red-200 hover:bg-red-900/40",
                    "focus-visible:outline-none focus-visible:ring-2",
                    "focus-visible:ring-red-500",
                    "disabled:opacity-60",
                  ].join(" ")}
                >
                  {t("tags.row.forceDelete")}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={remove.isPending}
                  className={[
                    "rounded-md border border-zinc-700 px-2 py-1",
                    "text-xs font-medium text-red-300 hover:bg-zinc-800",
                    "focus-visible:outline-none focus-visible:ring-2",
                    "focus-visible:ring-brand",
                    "disabled:opacity-60",
                  ].join(" ")}
                >
                  {remove.isPending
                    ? t("tags.row.deleting")
                    : t("tags.row.delete")}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {update.error && (
        <p role="alert" className="text-xs text-red-400">
          {update.error.message}
        </p>
      )}
      {inUse && (
        <p className="text-xs text-amber-300">{t("tags.row.inUseHint")}</p>
      )}
    </li>
  );
}
