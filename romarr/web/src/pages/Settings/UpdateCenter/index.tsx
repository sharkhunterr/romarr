/**
 * Settings > Update Center — the central manager for every
 * community-URL-driven resource the operator has registered.
 *
 * Same table for every ``resource_type``; column layout: name /
 * URL / kind / status / installed → available / actions
 * (Check now, Apply, Trust, Enable/Disable, Delete).
 *
 * The "Add community URL" affordance ships here too — the per-page
 * variants on Platforms / Custom Formats reuse the same modal
 * component pre-filled with their respective ``resource_type``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { AddCommunitySourceModal } from "./AddCommunitySourceModal";
import { CommunitySourceRow } from "./CommunitySourceRow";
import { SourceOrderPanel } from "./SourceOrderPanel";
import {
  useCommunitySources,
  type CommunityResourceType,
} from "@/lib/api/queries/community";

export function UpdateCenterPage(): ReactElement {
  const { t } = useTranslation("settings");
  const sources = useCommunitySources();
  const [addOpen, setAddOpen] = useState(false);
  const [prefilledType, setPrefilledType] = useState<
    CommunityResourceType | undefined
  >(undefined);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">
            {t("updateCenter.title")}
          </h1>
          <p className="mt-1 text-xs text-zinc-500">
            {t("updateCenter.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setPrefilledType(undefined);
            setAddOpen(true);
          }}
          className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300"
        >
          {t("updateCenter.addSource")}
        </button>
      </header>

      {sources.isPending && (
        <p className="text-xs text-zinc-500">{t("updateCenter.loading")}</p>
      )}
      {sources.isError && (
        <div
          role="alert"
          className="rounded-md border border-amber-800/50 bg-amber-950/30 p-4 text-xs"
        >
          <p className="font-medium text-amber-200">
            {t("updateCenter.loadErrorTitle")}
          </p>
          <p className="mt-1 text-amber-300/80">
            {sources.error.message}
          </p>
          <p className="mt-2 text-[0.65rem] text-zinc-400">
            {t("updateCenter.loadErrorHint")}
          </p>
        </div>
      )}
      {sources.isSuccess && sources.data.length === 0 && (
        <div className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 p-6 text-center">
          <p className="text-sm text-zinc-400">
            {t("updateCenter.empty.title")}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            {t("updateCenter.empty.hint")}
          </p>
        </div>
      )}
      {sources.isSuccess && sources.data.length > 0 && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {sources.data.map((src) => (
            <CommunitySourceRow key={src.id} source={src} />
          ))}
        </div>
      )}

      {/* Global rank for the platform materializer — only renders
          when at least 2 platform_pack sources exist. */}
      <SourceOrderPanel />

      {addOpen && (
        <AddCommunitySourceModal
          prefilledResourceType={prefilledType}
          onClose={() => setAddOpen(false)}
        />
      )}
    </div>
  );
}
