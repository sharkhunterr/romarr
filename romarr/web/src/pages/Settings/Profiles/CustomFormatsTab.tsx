/**
 * Profiles > Custom Formats tab (slice 64).
 *
 * Read-only audit list + delete; create / visual builder land
 * in a follow-up slice.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useCustomFormats } from "@/lib/api/queries/custom-formats";

import { CustomFormatRow } from "./CustomFormatRow";

export function CustomFormatsTab(): ReactElement {
  const { t } = useTranslation("settings");
  const formats = useCustomFormats();

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-400">
        {t("customFormats.subtitle")}
      </p>

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
