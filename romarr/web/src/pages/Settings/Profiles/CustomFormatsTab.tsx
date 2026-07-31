/**
 * Profiles > Custom Formats tab.
 *
 * Layout:
 *   1. Community-sources panel — every URL-imported CF pack the
 *      operator has registered, mirrored from the Update Center.
 *   2. Local list — every CF that ended up in the DB (from seeds,
 *      URL packs or manual creation), sorted by score desc.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useCustomFormats } from "@/lib/api/queries/custom-formats";
import { CommunitySourcesPanel } from "@/pages/Settings/UpdateCenter/CommunitySourcesPanel";

import { CustomFormatEditorModal } from "./CustomFormatEditorModal";
import { CustomFormatRow } from "./CustomFormatRow";

export function CustomFormatsTab(): ReactElement {
  const { t } = useTranslation("settings");
  const formats = useCustomFormats();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <CommunitySourcesPanel
        resourceType="custom_format"
        title={t("customFormats.communityPanelTitle")}
        subtitle={t("customFormats.communityPanelSubtitle")}
      />

      <div className="flex items-start justify-between gap-3 border-t border-zinc-800 pt-4">
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
        <CustomFormatEditorModal onClose={() => setCreateOpen(false)} />
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
