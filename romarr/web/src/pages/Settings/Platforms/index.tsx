/**
 * Settings > Platforms (slice 93).
 *
 * Read-only Platform Pack audit. Lists every persisted pack
 * (PackSummary), expandable per-row to fetch the full
 * application history (PackHistoryRow). Upload + re-apply
 * are admin write flows that land in a follow-up slice once
 * the multipart upload form is in place.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { usePlatformPacks } from "@/lib/api/queries/platform-packs";
import {
  usePlatforms,
  type Platform,
} from "@/lib/api/queries/platforms";

import { CommunitySourcesPanel } from "@/pages/Settings/UpdateCenter/CommunitySourcesPanel";

import { PackConfigPanel } from "./PackConfigPanel";
import { PackRow } from "./PackRow";
import { PlatformDetailModal } from "./PlatformDetailModal";

export function PlatformsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const packs = usePlatformPacks();
  const platforms = usePlatforms();
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Platform | null>(null);

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

      {/* Order: settings first (config + sources + history), the
          catalogue grid at the end — settings drive what lands in
          the catalogue, so surfacing them above is more actionable. */}
      <PackConfigPanel />

      <CommunitySourcesPanel
        resourceType="platform_pack"
        title={t("platforms.communityPanelTitle")}
        subtitle={t("platforms.communityPanelSubtitle")}
      />

      <section className="space-y-3">
        <header>
          <h3 className="text-sm font-medium text-zinc-100">
            {t("platforms.packs.heading")}
          </h3>
          <p className="text-[0.65rem] text-zinc-500">
            {t("platforms.packs.subhead")}
          </p>
        </header>
        {packs.isLoading && <ListSkeleton rows={3} />}
        {packs.isError && (
          <EmptyState
            title={t("platforms.empty.title")}
            description={packs.error.message}
          />
        )}
        {packs.isSuccess && packs.data.length === 0 && (
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
        {packs.isSuccess && packs.data.length > 0 && (
          <>
            <ul className="space-y-2">
              {packs.data.map((pack) => (
                <PackRow key={pack.pack_version} pack={pack} />
              ))}
            </ul>
            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
              {t("platforms.uploadHint")}
            </p>
          </>
        )}
      </section>

      {/* Slice 402 — catalogue grid: click a card to see every field
          of that Platform (aliases, format extensions, provider IDs,
          pack provenance). Moved to the bottom so the actionable
          settings come first. */}
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
        {platforms.isSuccess && filtered.length === 0 && (
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("platforms.catalogue.noMatches")}
          </p>
        )}
        {platforms.isSuccess && filtered.length > 0 && (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
            {filtered.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelected(p)}
                  className="flex h-full w-full flex-col gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-2.5 text-left transition-colors hover:border-brand/40 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                >
                  <span className="truncate text-xs font-medium text-zinc-100">
                    {p.short_name || p.name}
                  </span>
                  <span className="truncate font-mono text-[0.6rem] text-zinc-500">
                    {p.slug}
                  </span>
                  {p.manufacturer && (
                    <span className="mt-auto truncate text-[0.6rem] text-zinc-500">
                      {p.manufacturer}
                      {p.release_year && ` · ${p.release_year}`}
                    </span>
                  )}
                </button>
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
