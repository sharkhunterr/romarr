/**
 * Profiles > Naming tab (slice 91).
 *
 * Read-only audit list against /api/v3/rom/namingprofile.
 * Convention pill + template (truncated, monospace) + three
 * structural flags. Live preview lands in a follow-up slice
 * via POST /api/v3/rom/namingprofile/preview.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useDeleteNamingProfile,
  useNamingPreview,
  useNamingProfiles,
  type NamingProfile,
} from "@/lib/api/queries/naming-profiles";

import { CreateNamingProfileModal } from "./CreateNamingProfileModal";

interface RowProps {
  profile: NamingProfile;
}

function Pill(props: { label: string; tone?: "muted" | "amber" | "brand" }): ReactElement {
  const tone =
    props.tone === "amber"
      ? "bg-amber-950/40 text-amber-400"
      : props.tone === "brand"
        ? "bg-brand/20 text-brand"
        : "bg-zinc-800 text-zinc-300";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider ${tone}`}
    >
      {props.label}
    </span>
  );
}

function NamingProfileRow(props: RowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { profile } = props;
  const del = useDeleteNamingProfile();
  const preview = useNamingPreview();
  const [confirming, setConfirming] = useState(false);

  const handlePreview = (): void => {
    preview.mutate({
      profile: {
        name: profile.name,
        // ``convention`` on the read schema is a wider union
        // (no-intro / redump / tosec / goodtools / scene /
        // unknown). The create schema accepts the
        // engine-supported subset. The factory profiles ship
        // with values from the engine's whitelist, so the cast
        // is safe in practice.
        convention:
          profile.convention as unknown as "no-intro" | "redump" | "tosec" | "es-de" | "romm" | "custom",
        template: profile.template,
        platform_subfolder: profile.platform_subfolder,
        replace_illegal_chars: profile.replace_illegal_chars,
        multi_disc_subfolder: profile.multi_disc_subfolder,
      },
    });
  };

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">
            {profile.name}
          </p>
          <Pill label={profile.convention} tone="brand" />
          {profile.is_factory_default && (
            <Pill label={t("profiles.naming.factory")} />
          )}
          {profile.is_user_modified && (
            <Pill label={t("profiles.naming.modified")} tone="amber" />
          )}
        </div>

        <div className="space-y-1">
          <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
            {t("profiles.naming.template")}
          </p>
          <p className="truncate rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 font-mono text-[0.7rem] text-zinc-300">
            {profile.template}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
          {profile.platform_subfolder && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.naming.flags.platformSubfolder")}
            </span>
          )}
          {profile.replace_illegal_chars && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.naming.flags.replaceIllegal")}
            </span>
          )}
          {profile.multi_disc_subfolder && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.naming.flags.multiDiscSubfolder")}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handlePreview}
          disabled={preview.isPending}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-800",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {preview.isPending
            ? t("profiles.naming.preview.pending")
            : t("profiles.naming.preview.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={profile.is_factory_default}
          title={
            profile.is_factory_default
              ? t("profiles.naming.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("profiles.naming.delete.button")}
        </button>
      </div>

      {preview.isSuccess && preview.data && (
        <div className="mt-2 space-y-1">
          <p className="text-[0.6rem] uppercase tracking-wider text-zinc-500">
            {t("profiles.naming.preview.label")}
          </p>
          <p className="break-all rounded-md border border-emerald-900/40 bg-emerald-950/20 px-2 py-1.5 font-mono text-[0.7rem] text-emerald-200">
            {preview.data.rendered}
          </p>
        </div>
      )}

      {preview.isError && (
        <div
          role="alert"
          className="mt-2 rounded-md border border-red-900/50 bg-red-950/20 px-2 py-1.5 text-[0.7rem] text-red-300"
        >
          {t("profiles.naming.preview.error", {
            message: preview.error.message,
          })}
        </div>
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("profiles.naming.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("profiles.naming.delete.confirmBody", { name: profile.name })}
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
              {t("profiles.naming.delete.confirm")}
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
              {t("profiles.naming.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export function NamingTab(): ReactElement {
  const { t } = useTranslation("settings");
  const profiles = useNamingProfiles();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-zinc-400">
          {t("profiles.naming.subtitle")}
        </p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("profiles.naming.create.openButton")}
        </button>
      </div>

      {createOpen && (
        <CreateNamingProfileModal onClose={() => setCreateOpen(false)} />
      )}

      {profiles.isLoading && <ListSkeleton rows={3} />}
      {profiles.isError && (
        <EmptyState
          title={t("profiles.naming.empty.title")}
          description={profiles.error.message}
        />
      )}
      {profiles.isSuccess && profiles.data.length === 0 && (
        <EmptyState
          title={t("profiles.naming.empty.title")}
          description={t("profiles.naming.empty.body")}
        />
      )}
      {profiles.isSuccess && profiles.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {profiles.data.map((p) => (
              <NamingProfileRow key={p.id} profile={p} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("profiles.naming.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
