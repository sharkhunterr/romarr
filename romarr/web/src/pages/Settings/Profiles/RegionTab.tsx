/**
 * Profiles > Region tab (slice 90).
 *
 * Read-only audit list of every Region profile against
 * /api/v3/rom/regionprofile. Same pattern as QualityTab
 * (slice 65). Full editor (drag-list priorities + excluded
 * multi-select) lands in a follow-up slice.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useDeleteRegionProfile,
  useRegionProfiles,
  type RegionProfile,
} from "@/lib/api/queries/region-profiles";
import { regionLabelKey } from "@/lib/regions/catalogue";

import { CreateRegionProfileModal } from "./CreateRegionProfileModal";
import { EditRegionProfileModal } from "./EditRegionProfileModal";

interface RowProps {
  profile: RegionProfile;
}

function Pill(props: { label: string; tone?: "muted" | "amber" }): ReactElement {
  const tone =
    props.tone === "amber"
      ? "bg-amber-950/40 text-amber-400"
      : "bg-zinc-800 text-zinc-300";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider ${tone}`}
    >
      {props.label}
    </span>
  );
}

function _regionPillLabel(t: (k: string) => string, code: string): string {
  // Catalogue codes get the localised label; legacy / custom codes
  // fall back to the raw code so nothing renders as a missing key.
  const key = regionLabelKey(code);
  if (key === code) return code;
  return t(`profiles.region.catalogue.${key}`);
}

function RegionProfileRow(props: RowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { profile } = props;
  const del = useDeleteRegionProfile();
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">
            {profile.name}
          </p>
          {profile.is_factory_default && (
            <Pill label={t("profiles.region.factory")} />
          )}
          {profile.is_user_modified && (
            <Pill label={t("profiles.region.modified")} tone="amber" />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
          <span className="text-zinc-500">
            {t("profiles.region.priorities")}:
          </span>
          {profile.priorities.length === 0 ? (
            <span className="text-zinc-600">—</span>
          ) : (
            profile.priorities.map((code) => (
              <Pill key={code} label={_regionPillLabel(t, code)} />
            ))
          )}
        </div>

        {profile.exclude_regions.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
            <span className="text-zinc-500">
              {t("profiles.region.excluded")}:
            </span>
            {profile.exclude_regions.map((code) => (
              <Pill key={code} label={_regionPillLabel(t, code)} tone="amber" />
            ))}
          </div>
        )}

        <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
          {profile.allow_fallback_outside_priorities
            ? t("profiles.region.fallback")
            : t("profiles.region.noFallback")}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {t("profiles.region.edit.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={profile.is_factory_default}
          title={
            profile.is_factory_default
              ? t("profiles.region.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("profiles.region.delete.button")}
        </button>
      </div>

      {editing && (
        <EditRegionProfileModal
          profile={profile}
          onClose={() => setEditing(false)}
        />
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("profiles.region.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("profiles.region.delete.confirmBody", { name: profile.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={() => del.mutate(profile.id)}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("profiles.region.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("profiles.region.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export function RegionTab(): ReactElement {
  const { t } = useTranslation("settings");
  const profiles = useRegionProfiles();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-zinc-400">{t("profiles.region.subtitle")}</p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("profiles.region.create.openButton")}
        </button>
      </div>

      {createOpen && (
        <CreateRegionProfileModal onClose={() => setCreateOpen(false)} />
      )}

      {profiles.isLoading && <ListSkeleton rows={3} />}
      {profiles.isError && (
        <EmptyState
          title={t("profiles.region.empty.title")}
          description={profiles.error.message}
        />
      )}
      {profiles.isSuccess && profiles.data.length === 0 && (
        <EmptyState
          title={t("profiles.region.empty.title")}
          description={t("profiles.region.empty.body")}
        />
      )}
      {profiles.isSuccess && profiles.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {profiles.data.map((p) => (
              <RegionProfileRow key={p.id} profile={p} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("profiles.region.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
