/**
 * Profiles > Custom Formats tab.
 *
 * Read-only audit list + delete (slice 64) + visual builder
 * (slice 305 / spec 014 T097): operators add a new Custom
 * Format from a structured form (name + score + conditions).
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useCustomFormats } from "@/lib/api/queries/custom-formats";

import { CreateCustomFormatModal } from "./CreateCustomFormatModal";
import { CustomFormatRow } from "./CustomFormatRow";

export function CustomFormatsTab(): ReactElement {
  const { t } = useTranslation("settings");
  const formats = useCustomFormats();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-zinc-400">
          {t("customFormats.subtitle")}
        </p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("customFormats.create.openButton")}
        </button>
      </div>

      {createOpen && (
        <CreateCustomFormatModal onClose={() => setCreateOpen(false)} />
      )}

      {formats.isLoading && <ListSkeleton rows={4} />}
      {formats.isError && (
        <EmptyState
          title={t("customFormats.empty.title")}
          description={formats.error.message}
        />
      )}
      {formats.isSuccess && formats.data.length === 0 && (
        <EmptyState
          title={t("customFormats.empty.title")}
          description={t("customFormats.empty.body")}
        />
      )}
      {formats.isSuccess && formats.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {[...formats.data]
              .sort((a, b) => b.score - a.score)
              .map((f) => (
                <CustomFormatRow key={f.id} format={f} />
              ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("customFormats.builderHint")}
          </p>
        </>
      )}
    </div>
  );
}
