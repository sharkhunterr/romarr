/**
 * Settings > Platforms (slice 93).
 *
 * Read-only Platform Pack audit. Lists every persisted pack
 * (PackSummary), expandable per-row to fetch the full
 * application history (PackHistoryRow). Upload + re-apply
 * are admin write flows that land in a follow-up slice once
 * the multipart upload form is in place.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { usePlatformPacks } from "@/lib/api/queries/platform-packs";

import { PackRow } from "./PackRow";

export function PlatformsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const packs = usePlatformPacks();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("platforms.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("platforms.subtitle")}
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
        <EmptyState
          title={t("platforms.empty.title")}
          description={t("platforms.empty.body")}
        />
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
    </div>
  );
}
