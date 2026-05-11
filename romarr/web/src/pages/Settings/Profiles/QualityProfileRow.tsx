/**
 * One row in the Quality Profiles audit list (slice 65).
 *
 * Read-only audit view: name + factory/modified pills +
 * preferred / upgrade-until format chips + allowed-format
 * list + DAT-verified / archive-double-compression toggles
 * (display-only). Delete gated on `is_factory_default` —
 * operators reset those by re-running the seed migration.
 *
 * Edit form (drag-drop allowed list + format pickers) is
 * deferred to a follow-up slice.
 */

import { Pencil } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteQualityProfile,
  type QualityProfile,
} from "@/lib/api/queries/quality-profiles";

import { CreateQualityProfileModal } from "./CreateQualityProfileModal";

interface QualityProfileRowProps {
  profile: QualityProfile;
}

function FormatChip(props: { label: string; tone: "brand" | "amber" | "muted" }): ReactElement {
  const tones = {
    brand: "bg-brand/20 text-brand",
    amber: "bg-amber-950/40 text-amber-400",
    muted: "bg-zinc-800 text-zinc-300",
  } as const;
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[0.65rem] font-medium ${tones[props.tone]}`}
    >
      {props.label}
    </span>
  );
}

export function QualityProfileRow(
  props: QualityProfileRowProps,
): ReactElement {
  const { profile } = props;
  const { t } = useTranslation("settings");
  const del = useDeleteQualityProfile();

  const [confirming, setConfirming] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  function confirmDelete(): void {
    del.mutate(profile.id);
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {profile.name}
            </p>
            {profile.is_factory_default && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
                {t("profiles.quality.factory")}
              </span>
            )}
            {profile.is_user_modified && (
              <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-amber-400">
                {t("profiles.quality.modified")}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[0.65rem]">
            <span className="text-zinc-500">
              {t("profiles.quality.preferred")}:
            </span>
            <FormatChip label={profile.preferred_format} tone="brand" />
            <span className="text-zinc-500">
              {t("profiles.quality.upgradeUntil")}:
            </span>
            <FormatChip label={profile.upgrade_until_format} tone="amber" />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
            <span className="text-zinc-500">
              {t("profiles.quality.allowedFormats")}:
            </span>
            {profile.allowed_formats.length === 0 ? (
              <span className="text-zinc-600">—</span>
            ) : (
              profile.allowed_formats.map((format) => (
                <FormatChip key={format} label={format} tone="muted" />
              ))
            )}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
            {profile.require_dat_verified && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
                ✓ {t("profiles.quality.datRequired")}
              </span>
            )}
            {profile.allow_archive_double_compression && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
                ✓ {t("profiles.quality.archiveDouble")}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className={[
            "min-h-[36px] inline-flex items-center gap-1 rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          <Pencil size={12} aria-hidden="true" />
          {t("profiles.quality.edit.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={profile.is_factory_default}
          title={
            profile.is_factory_default
              ? t("profiles.quality.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("profiles.quality.delete.button")}
        </button>
      </div>

      {editOpen && (
        <CreateQualityProfileModal
          profile={profile}
          onClose={() => setEditOpen(false)}
        />
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("profiles.quality.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("profiles.quality.delete.confirmBody", { name: profile.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("profiles.quality.delete.confirm")}
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
              {t("profiles.quality.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
