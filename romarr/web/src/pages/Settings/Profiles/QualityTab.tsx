/**
 * Profiles > Quality tab (slice 65).
 *
 * Read-only audit list of every Quality profile against
 * /api/v3/qualityprofile. Per-row delete (gated on
 * `is_factory_default`) is the only mutation today; the
 * full editor lands in a follow-up slice.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useQualityProfiles } from "@/lib/api/queries/quality-profiles";

import { QualityProfileEditorModal } from "./QualityProfileEditorModal";
import { QualityProfileRow } from "./QualityProfileRow";

export function QualityTab(): ReactElement {
  const { t } = useTranslation("settings");
  const profiles = useQualityProfiles();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-zinc-400">
          {t("profiles.quality.subtitle")}
        </p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("profiles.quality.create.openButton")}
        </button>
      </div>

      {createOpen && (
        <QualityProfileEditorModal onClose={() => setCreateOpen(false)} />
      )}

      {profiles.isLoading && <ListSkeleton rows={3} />}
      {profiles.isError && (
        <EmptyState
          title={t("profiles.quality.empty.title")}
          description={profiles.error.message}
        />
      )}
      {profiles.isSuccess && profiles.data.length === 0 && (
        <EmptyState
          title={t("profiles.quality.empty.title")}
          description={t("profiles.quality.empty.body")}
        />
      )}
      {profiles.isSuccess && profiles.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {profiles.data.map((p) => (
              <QualityProfileRow key={p.id} profile={p} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("profiles.quality.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
