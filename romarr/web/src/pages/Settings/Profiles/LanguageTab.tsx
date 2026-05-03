/**
 * Profiles > Language tab (slice 90).
 *
 * Read-only audit list against /api/v3/rom/languageprofile.
 * Same shape as RegionTab — required vs preferred lists,
 * exclude-japanese-only flag, factory-blocked delete.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useDeleteLanguageProfile,
  useLanguageProfiles,
  type LanguageProfile,
} from "@/lib/api/queries/language-profiles";

interface RowProps {
  profile: LanguageProfile;
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

function LanguageProfileRow(props: RowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { profile } = props;
  const del = useDeleteLanguageProfile();
  const [confirming, setConfirming] = useState(false);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">
            {profile.name}
          </p>
          {profile.is_factory_default && (
            <Pill label={t("profiles.language.factory")} />
          )}
          {profile.is_user_modified && (
            <Pill label={t("profiles.language.modified")} tone="amber" />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
          <span className="text-zinc-500">
            {t("profiles.language.required")}:
          </span>
          {profile.required_languages.length === 0 ? (
            <span className="text-zinc-600">—</span>
          ) : (
            profile.required_languages.map((code) => (
              <Pill key={`req-${code}`} label={code} tone="amber" />
            ))
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
          <span className="text-zinc-500">
            {t("profiles.language.preferred")}:
          </span>
          {profile.preferred_languages.length === 0 ? (
            <span className="text-zinc-600">—</span>
          ) : (
            profile.preferred_languages.map((code) => (
              <Pill key={`pref-${code}`} label={code} tone="brand" />
            ))
          )}
        </div>

        {profile.exclude_japanese_only && (
          <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
            ✓ {t("profiles.language.excludeJa")}
          </p>
        )}
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={profile.is_factory_default}
          title={
            profile.is_factory_default
              ? t("profiles.language.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("profiles.language.delete.button")}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("profiles.language.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("profiles.language.delete.confirmBody", { name: profile.name })}
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
              {t("profiles.language.delete.confirm")}
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
              {t("profiles.language.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export function LanguageTab(): ReactElement {
  const { t } = useTranslation("settings");
  const profiles = useLanguageProfiles();

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-400">{t("profiles.language.subtitle")}</p>

      {profiles.isLoading && <ListSkeleton rows={3} />}
      {profiles.isError && (
        <EmptyState
          title={t("profiles.language.empty.title")}
          description={profiles.error.message}
        />
      )}
      {profiles.isSuccess && profiles.data.length === 0 && (
        <EmptyState
          title={t("profiles.language.empty.title")}
          description={t("profiles.language.empty.body")}
        />
      )}
      {profiles.isSuccess && profiles.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {profiles.data.map((p) => (
              <LanguageProfileRow key={p.id} profile={p} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("profiles.language.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
