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

import { useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useIndexers } from "@/lib/api/queries/indexers";

import { ApplicationsPanel } from "./ApplicationsPanel";
import { IndexerRow } from "./IndexerRow";

export function IndexersPage(): ReactElement {
  const { t } = useTranslation("settings");
  const indexers = useIndexers();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawQuery = searchParams.get("q") ?? "";
  const queryNormalized = rawQuery.trim().toLowerCase();

  const setQuery = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next.trim() === "") params.delete("q");
        else params.set("q", next);
        return params;
      },
      { replace: true },
    );
  };

  const filtered = useMemo(() => {
    if (!indexers.data) return [];
    if (queryNormalized.length === 0) return indexers.data;
    return indexers.data.filter(
      (indexer) =>
        indexer.name.toLowerCase().includes(queryNormalized) ||
        indexer.url.toLowerCase().includes(queryNormalized),
    );
  }, [indexers.data, queryNormalized]);

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
        <>
          <label className="block">
            <span className="sr-only">{t("indexers.search.label")}</span>
            <input
              type="search"
              value={rawQuery}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("indexers.search.placeholder")}
              aria-label={t("indexers.search.label")}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>
          {filtered.length === 0 ? (
            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
              {t("indexers.search.noMatches")}
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((indexer) => (
                <IndexerRow key={indexer.id} indexer={indexer} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
