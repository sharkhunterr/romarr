/**
 * Profiles > Dump tab (slice 91).
 *
 * Read-only audit list against /api/v3/rom/dumpprofile.
 * Allowed-status pills + the four allow_* flag toggles +
 * prefer_revision picker. Same delete-gated-on-factory
 * pattern as the other profile tabs.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useDeleteDumpProfile,
  useDumpProfiles,
  type DumpProfile,
} from "@/lib/api/queries/dump-profiles";

import { CreateDumpProfileModal } from "./CreateDumpProfileModal";

interface RowProps {
  profile: DumpProfile;
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

function DumpProfileRow(props: RowProps): ReactElement {
  const { t } = useTranslation("settings");
  const { profile } = props;
  const del = useDeleteDumpProfile();
  const [confirming, setConfirming] = useState(false);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">
            {profile.name}
          </p>
          {profile.is_factory_default && (
            <Pill label={t("profiles.dump.factory")} />
          )}
          {profile.is_user_modified && (
            <Pill label={t("profiles.dump.modified")} tone="amber" />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
          <span className="text-zinc-500">{t("profiles.dump.allowed")}:</span>
          {profile.allowed_dump_status.length === 0 ? (
            <span className="text-zinc-600">—</span>
          ) : (
            profile.allowed_dump_status.map((s) => <Pill key={s} label={s} />)
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem]">
          <span className="text-zinc-500">
            {t("profiles.dump.preferRevision")}:
          </span>
          <Pill label={profile.prefer_revision} tone="brand" />
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
          {profile.allow_proto_beta && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.dump.flags.protoBeta")}
            </span>
          )}
          {profile.allow_hacks && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.dump.flags.hacks")}
            </span>
          )}
          {profile.allow_trainers && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.dump.flags.trainers")}
            </span>
          )}
          {profile.allow_translations && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              ✓ {t("profiles.dump.flags.translations")}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={profile.is_factory_default}
          title={
            profile.is_factory_default
              ? t("profiles.dump.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("profiles.dump.delete.button")}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("profiles.dump.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("profiles.dump.delete.confirmBody", { name: profile.name })}
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
              {t("profiles.dump.delete.confirm")}
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
              {t("profiles.dump.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export function DumpTab(): ReactElement {
  const { t } = useTranslation("settings");
  const profiles = useDumpProfiles();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-zinc-400">
          {t("profiles.dump.subtitle")}
        </p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("profiles.dump.create.openButton")}
        </button>
      </div>

      {createOpen && (
        <CreateDumpProfileModal onClose={() => setCreateOpen(false)} />
      )}

      {profiles.isLoading && <ListSkeleton rows={3} />}
      {profiles.isError && (
        <EmptyState
          title={t("profiles.dump.empty.title")}
          description={profiles.error.message}
        />
      )}
      {profiles.isSuccess && profiles.data.length === 0 && (
        <EmptyState
          title={t("profiles.dump.empty.title")}
          description={t("profiles.dump.empty.body")}
        />
      )}
      {profiles.isSuccess && profiles.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {profiles.data.map((p) => (
              <DumpProfileRow key={p.id} profile={p} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("profiles.dump.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
