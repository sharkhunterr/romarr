/**
 * Settings > Platforms — the community-first catalogue view.
 *
 * Structure :
 *   1. Empty-state banner if zero platforms are defined (points at
 *      the fetch / import paths above).
 *   2. Community sources panel + global rank editor.
 *   3. Platform catalogue grid — filterable, cards show name +
 *      slug + manufacturer + source badges (one per source that
 *      has contributed to the slug via
 *      ``platform_source_contribution``). Click opens the detail
 *      modal.
 *
 * Removed with the community-first model :
 *   * "Platform Packs" application history (PackRow list) — the
 *     Update Center now surfaces every relevant apply.
 *   * PackConfigPanel (builtin toggle) — builtin is disabled by
 *     default per migration 0042; the config remains reachable
 *     via API for the rare operator who reactivates it.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useCommunitySources } from "@/lib/api/queries/community";
import {
  usePlatforms,
  type Platform,
} from "@/lib/api/queries/platforms";
import { CommunitySourcesPanel } from "@/pages/Settings/UpdateCenter/CommunitySourcesPanel";
import { SourceOrderPanel } from "@/pages/Settings/UpdateCenter/SourceOrderPanel";

import { PlatformCard } from "./PlatformCard";
import { PlatformDetailModal } from "./PlatformDetailModal";

export function PlatformsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const platforms = usePlatforms();
  const platformSources = useCommunitySources("platform_pack");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Platform | null>(null);

  const sourcesById = useMemo(() => {
    const m = new Map<number, string>();
    (platformSources.data ?? []).forEach((s) => m.set(s.id, s.name));
    return m;
  }, [platformSources.data]);

  const filtered = useMemo(() => {
    const list = platforms.data ?? [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((p) => {
      const blobs: string[] = [
        p.slug,
        p.name,
        p.short_name ?? "",
        p.manufacturer ?? "",
        ...(p.aliases ?? []),
      ];
      return blobs.some((b) => b.toLowerCase().includes(needle));
    });
  }, [platforms.data, filter]);

  const isEmpty =
    platforms.isSuccess && (platforms.data ?? []).length === 0;

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("platforms.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("platforms.subtitle")}
        </p>
      </header>

      {isEmpty && (
        <div className="rounded-md border border-amber-800/50 bg-amber-950/20 p-4">
          <p className="text-sm font-medium text-amber-200">
            {t("platforms.emptyBanner.title")}
          </p>
          <p className="mt-1 text-xs text-amber-300/80">
            {t("platforms.emptyBanner.body")}
          </p>
          <p className="mt-2 text-[0.65rem] text-zinc-400">
            {t("platforms.emptyBanner.hint")}
          </p>
        </div>
      )}

      <CommunitySourcesPanel
        resourceType="platform_pack"
        title={t("platforms.communityPanelTitle")}
        subtitle={t("platforms.communityPanelSubtitle")}
      />

      <SourceOrderPanel />

      {/* Catalogue */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 className="text-sm font-medium text-zinc-100">
              {t("platforms.catalogue.heading")}
            </h3>
            <p className="text-[0.65rem] text-zinc-500">
              {t("platforms.catalogue.subhead", {
                count: platforms.data?.length ?? 0,
              })}
            </p>
          </div>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("platforms.catalogue.filterPlaceholder")}
            className="w-full max-w-xs rounded-md bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
        </div>

        {platforms.isLoading && <ListSkeleton rows={4} />}
        {platforms.isError && (
          <EmptyState
            title={t("platforms.catalogue.loadError")}
            description={platforms.error.message}
          />
        )}
        {platforms.isSuccess && filtered.length === 0 && !isEmpty && (
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("platforms.catalogue.noMatches")}
          </p>
        )}
        {platforms.isSuccess && filtered.length > 0 && (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((p) => (
              <li key={p.id}>
                <PlatformCard
                  platform={p}
                  sourceNames={sourcesById}
                  onClick={() => setSelected(p)}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected !== null && (
        <PlatformDetailModal
          platform={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
