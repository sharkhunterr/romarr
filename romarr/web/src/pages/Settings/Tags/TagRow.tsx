/**
 * Single tag row with inline edit + delete.
 *
 * Click "Edit" to swap the static label / color into editable
 * inputs; "Save" runs `useUpdateTag`; "Delete" runs
 * `useDeleteTag`. The 409 "tag_in_use" path prompts the
 * operator to confirm a force-delete.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { useState, type ReactElement } from "react";

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
      window.confirm(
        `Tag "${tag.label}" is currently assigned to one or more entities. Force-delete the assignments?`,
      )
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
                className={[
                  "h-8 w-12 rounded-md bg-zinc-950",
                  "ring-1 ring-inset ring-zinc-700",
                ].join(" ")}
              />
            </div>
          ) : (
            <>
              <p className="truncate text-sm font-medium text-zinc-100">
                {tag.label}
              </p>
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
                {update.isPending ? "…" : "Save"}
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
                Cancel
              </button>
            </>
          ) : (
            <>
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
                Edit
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
                  Force delete
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
                  {remove.isPending ? "…" : "Delete"}
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
        <p className="text-xs text-amber-300">
          Tag is assigned to one or more entities. Click "Force
          delete" to cascade-remove the assignments.
        </p>
      )}
    </li>
  );
}
