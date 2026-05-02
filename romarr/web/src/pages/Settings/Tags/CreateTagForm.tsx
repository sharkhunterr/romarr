/**
 * Create-tag form (Settings > Tags).
 *
 * Three fields: name (slug, lowercase letters + digits + hyphens),
 * label (human-friendly), color (hex with brand-default
 * #9BBC0F). The submit handler runs the slice 51
 * useCreateTag mutation; on success the form clears and the
 * tag list re-queries automatically (mutation onSuccess
 * invalidates).
 *
 * Strings resolve through `settings:tags.create.*` (slice 66).
 */

import { type FormEvent, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useCreateTag } from "@/lib/api/queries/tags";

const DEFAULT_COLOR = "#9BBC0F";

export function CreateTagForm(): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateTag();
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      { name, label, color },
      {
        onSuccess: () => {
          setName("");
          setLabel("");
          setColor(DEFAULT_COLOR);
        },
      },
    );
  }

  let errorMessage: string | null = null;
  if (create.error !== null) {
    if (create.error.errorCode === "tag_name_conflict") {
      errorMessage = t("tags.create.errors.conflict");
    } else {
      errorMessage = create.error.message;
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className={[
        "rounded-md border border-zinc-800 bg-zinc-900/60",
        "p-4 space-y-3",
      ].join(" ")}
    >
      <h3 className="text-sm font-medium text-zinc-100">
        {t("tags.create.heading")}
      </h3>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label
            htmlFor="tag-name"
            className="block text-[0.7rem] font-medium text-zinc-400"
          >
            {t("tags.create.slug")}
          </label>
          <input
            id="tag-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            pattern="^[a-z0-9-]+$"
            placeholder={t("tags.create.slugPlaceholder")}
            className={[
              "w-full rounded-md bg-zinc-950 px-2.5 py-1.5",
              "text-xs font-mono text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          />
        </div>

        <div className="space-y-1">
          <label
            htmlFor="tag-label"
            className="block text-[0.7rem] font-medium text-zinc-400"
          >
            {t("tags.create.label")}
          </label>
          <input
            id="tag-label"
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            required
            placeholder={t("tags.create.labelPlaceholder")}
            className={[
              "w-full rounded-md bg-zinc-950 px-2.5 py-1.5",
              "text-xs text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          />
        </div>

        <div className="space-y-1">
          <label
            htmlFor="tag-color"
            className="block text-[0.7rem] font-medium text-zinc-400"
          >
            {t("tags.create.color")}
          </label>
          <input
            id="tag-color"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className={[
              "h-8 w-full rounded-md bg-zinc-950",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          />
        </div>
      </div>

      {errorMessage !== null && (
        <p role="alert" className="text-xs text-red-400">
          {errorMessage}
        </p>
      )}

      <button
        type="submit"
        disabled={create.isPending}
        className={[
          "rounded-md bg-brand px-3 py-1.5 text-xs font-medium",
          "text-zinc-900 hover:bg-brand-300",
          "focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-60",
        ].join(" ")}
      >
        {create.isPending
          ? t("tags.create.submitting")
          : t("tags.create.submit")}
      </button>
    </form>
  );
}
