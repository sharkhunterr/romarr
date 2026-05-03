/**
 * Settings > Indexers (slice 60).
 *
 * Operator-facing list of every Newznab + Torznab indexer
 * Romarr knows about. The MVP slice ships:
 *   * GET /api/v3/indexer — full list with health badges.
 *   * POST /api/v3/indexer/{id}/test — connectivity probe.
 *   * DELETE /api/v3/indexer/{id} — admin-only removal.
 *
 * The "Add new" form is deferred: IndexerCreate carries
 * ~17 required fields and the canonical UX is to let
 * Prowlarr push sources via /api/v3/applications. A "Sync
 * Prowlarr" button + manual-add modal land in a follow-up
 * slice.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useIndexers } from "@/lib/api/queries/indexers";

import { ApplicationsPanel } from "./ApplicationsPanel";
import { IndexerRow } from "./IndexerRow";

export function IndexersPage(): ReactElement {
  const { t } = useTranslation("settings");
  const indexers = useIndexers();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("indexers.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{t("indexers.subtitle")}</p>
      </header>

      <ApplicationsPanel />

      {indexers.isLoading && <ListSkeleton rows={3} />}
      {indexers.isError && (
        <EmptyState
          title={t("indexers.empty.title")}
          description={indexers.error.message}
        />
      )}
      {indexers.isSuccess && indexers.data.length === 0 && (
        <EmptyState
          title={t("indexers.empty.title")}
          description={t("indexers.empty.body")}
        />
      )}
      {indexers.isSuccess && indexers.data.length > 0 && (
        <ul className="space-y-2">
          {indexers.data.map((indexer) => (
            <IndexerRow key={indexer.id} indexer={indexer} />
          ))}
        </ul>
      )}
    </div>
  );
}
