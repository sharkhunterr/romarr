/**
 * Settings > Metadata Sources (slice 63).
 *
 * Lists every metadata provider Romarr can pull from. The MVP
 * slice ships:
 *   * GET /api/v3/metadata/provider — full list with health.
 *   * PUT /api/v3/metadata/provider/{name} — enable / priority.
 *   * POST /api/v3/metadata/provider/{name}/test — live probe.
 *
 * The drag-and-drop per-field provider editor (against
 * /api/v3/metadata/field-priority) is deferred to a follow-up
 * slice — surface a hint at the bottom of the page so the
 * operator knows where to look once it ships.
 *
 * Providers are sorted by `priority_global` ascending so the
 * highest-authority sources sit at the top of the list.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useMetadataProviders } from "@/lib/api/queries/metadata-sources";

import { ProviderRow } from "./ProviderRow";

export function MetadataSourcesPage(): ReactElement {
  const { t } = useTranslation("settings");
  const providers = useMetadataProviders();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("metadataSources.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("metadataSources.subtitle")}
        </p>
      </header>

      {providers.isLoading && <ListSkeleton rows={4} />}
      {providers.isError && (
        <EmptyState
          title={t("metadataSources.empty.title")}
          description={providers.error.message}
        />
      )}
      {providers.isSuccess && providers.data.length === 0 && (
        <EmptyState
          title={t("metadataSources.empty.title")}
          description={t("metadataSources.empty.body")}
        />
      )}
      {providers.isSuccess && providers.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {[...providers.data]
              .sort((a, b) => a.priority_global - b.priority_global)
              .map((p) => (
                <ProviderRow key={p.provider_name} provider={p} />
              ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("metadataSources.fieldPriorityHint")}
          </p>
        </>
      )}
    </div>
  );
}
