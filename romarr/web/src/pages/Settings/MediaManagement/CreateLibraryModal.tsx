/**
 * CreateLibraryModal (slice 285).
 *
 * Single-step Add-new flow for the spec 009 library surface.
 * Operator picks a name + absolute path + the five profile FKs
 * (quality / region / dump / language / naming) + a small set
 * of essential toggles (use_hardlinks, monitored_default,
 * lifecycle_policy). The remaining ``LibraryCreate`` fields
 * (RomM exporter creds, archive preservation, per-platform
 * Launchbox, scan_poll_seconds, …) inherit the schema defaults
 * so the form stays focused on the bare minimum operators need
 * to wire a fresh library.
 *
 * Profile selects load from the corresponding read endpoints;
 * each defaults to the first profile in the list (the
 * factory-default). The name + absolute path are required.
 *
 * Strings resolve through ``settings:mediaManagement.create.*``.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateLibrary,
  useUpdateLibrary,
  type Library,
  type LibraryCreate,
  type LibraryLifecyclePolicy,
} from "@/lib/api/queries/libraries";
import { useDumpProfiles } from "@/lib/api/queries/dump-profiles";
import { useLanguageProfiles } from "@/lib/api/queries/language-profiles";
import { useNamingProfiles } from "@/lib/api/queries/naming-profiles";
import { useQualityProfiles } from "@/lib/api/queries/quality-profiles";
import { useRegionProfiles } from "@/lib/api/queries/region-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateLibraryModalProps {
  onClose: () => void;
  // Slice 398 — when set, the modal is in edit mode: form
  // pre-fills from the library, the title says "Edit", and
  // submit fires PUT instead of POST.
  library?: Library;
}

const _LIFECYCLE_POLICIES: ReadonlyArray<LibraryLifecyclePolicy> = [
  "hardlink_and_seed",
  "move_and_remove",
  "copy_and_keep",
];

interface ProfileOption {
  id: number;
  name: string;
}

function _profilePickFirst(
  options: ReadonlyArray<ProfileOption>,
): number | null {
  return options.length > 0 ? options[0]!.id : null;
}

export function CreateLibraryModal(
  props: CreateLibraryModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateLibrary();
  const update = useUpdateLibrary();
  const pushToast = useToastStore((s) => s.push);
  const editing = props.library ?? null;

  const qualityProfiles = useQualityProfiles();
  const regionProfiles = useRegionProfiles();
  const dumpProfiles = useDumpProfiles();
  const languageProfiles = useLanguageProfiles();
  const namingProfiles = useNamingProfiles();

  const [name, setName] = useState(editing?.name ?? "");
  const [path, setPath] = useState(editing?.path ?? "");
  const [qualityId, setQualityId] = useState<number | null>(
    editing?.quality_profile_id ?? null,
  );
  const [regionId, setRegionId] = useState<number | null>(
    editing?.region_profile_id ?? null,
  );
  const [dumpId, setDumpId] = useState<number | null>(
    editing?.dump_profile_id ?? null,
  );
  const [languageId, setLanguageId] = useState<number | null>(
    editing?.language_profile_id ?? null,
  );
  const [namingId, setNamingId] = useState<number | null>(
    editing?.naming_profile_id ?? null,
  );
  const [lifecyclePolicy, setLifecyclePolicy] =
    useState<LibraryLifecyclePolicy>(
      (editing?.lifecycle_policy as LibraryLifecyclePolicy) ??
        "hardlink_and_seed",
    );
  const [useHardlinks, setUseHardlinks] = useState(
    editing?.use_hardlinks ?? true,
  );
  const [monitoredDefault, setMonitoredDefault] = useState(
    editing?.monitored_default ?? true,
  );

  // When each profile list resolves, default to the first item so
  // the form is submittable on first interaction. The operator
  // can still change picks before submitting.
  useEffect(() => {
    if (qualityId === null && qualityProfiles.data) {
      setQualityId(_profilePickFirst(qualityProfiles.data));
    }
  }, [qualityId, qualityProfiles.data]);
  useEffect(() => {
    if (regionId === null && regionProfiles.data) {
      setRegionId(_profilePickFirst(regionProfiles.data));
    }
  }, [regionId, regionProfiles.data]);
  useEffect(() => {
    if (dumpId === null && dumpProfiles.data) {
      setDumpId(_profilePickFirst(dumpProfiles.data));
    }
  }, [dumpId, dumpProfiles.data]);
  useEffect(() => {
    if (languageId === null && languageProfiles.data) {
      setLanguageId(_profilePickFirst(languageProfiles.data));
    }
  }, [languageId, languageProfiles.data]);
  useEffect(() => {
    if (namingId === null && namingProfiles.data) {
      // Slice 387 — Sonarr-style preference: prefer the
      // "RomM Passthrough" / romm-convention naming so files
      // land with names a parallel RomM scan recognises out
      // of the box. Falls back to the first profile when no
      // romm-shaped one is configured.
      const list = namingProfiles.data;
      const romm = list.find(
        (p) =>
          ("convention" in p && p.convention === "romm") ||
          /romm/i.test(p.name),
      );
      setNamingId(romm?.id ?? _profilePickFirst(list));
    }
  }, [namingId, namingProfiles.data]);

  const submitting = create.isPending || update.isPending;
  const profilesReady =
    qualityId !== null &&
    regionId !== null &&
    dumpId !== null &&
    languageId !== null &&
    namingId !== null;
  const canSubmit =
    name.trim().length > 0 && path.trim().length > 0 && profilesReady;

  function commit(): void {
    if (!canSubmit) return;
    const payload: LibraryCreate = {
      name: name.trim(),
      path: path.trim(),
      quality_profile_id: qualityId!,
      region_profile_id: regionId!,
      dump_profile_id: dumpId!,
      language_profile_id: languageId!,
      naming_profile_id: namingId!,
      lifecycle_policy: lifecyclePolicy,
      use_hardlinks: useHardlinks,
      monitored_default: monitoredDefault,
    };
    const onError = (err: { message: string; details?: unknown }) => {
      const apiDetails =
        typeof err.details === "string"
          ? (err.details as string)
          : null;
      pushToast({
        kind: "error",
        title: editing
          ? t("mediaManagement.edit.errorTitle")
          : t("mediaManagement.create.errorTitle"),
        description: apiDetails ?? err.message,
      });
    };
    if (editing) {
      update.mutate(
        { id: editing.id, payload },
        {
          onSuccess: (saved) => {
            pushToast({
              kind: "success",
              title: t("mediaManagement.edit.successTitle"),
              description: t("mediaManagement.edit.successBody", {
                name: saved.name,
              }),
            });
            props.onClose();
          },
          onError,
        },
      );
      return;
    }
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("mediaManagement.create.successTitle"),
          description: t("mediaManagement.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError,
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={
        editing
          ? t("mediaManagement.edit.modalTitle")
          : t("mediaManagement.create.modalTitle")
      }
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {editing
              ? t("mediaManagement.edit.modalTitle")
              : t("mediaManagement.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {editing
              ? t("mediaManagement.edit.subhead")
              : t("mediaManagement.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("mediaManagement.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("mediaManagement.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("mediaManagement.create.pathLabel")}
            </span>
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/data/roms/megadrive"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("mediaManagement.create.pathHint")}
            </p>
          </label>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <ProfileSelect
              label={t("mediaManagement.create.qualityLabel")}
              options={qualityProfiles.data ?? []}
              value={qualityId}
              onChange={setQualityId}
              disabled={submitting || !qualityProfiles.isSuccess}
            />
            <ProfileSelect
              label={t("mediaManagement.create.regionLabel")}
              options={regionProfiles.data ?? []}
              value={regionId}
              onChange={setRegionId}
              disabled={submitting || !regionProfiles.isSuccess}
            />
            <ProfileSelect
              label={t("mediaManagement.create.dumpLabel")}
              options={dumpProfiles.data ?? []}
              value={dumpId}
              onChange={setDumpId}
              disabled={submitting || !dumpProfiles.isSuccess}
            />
            <ProfileSelect
              label={t("mediaManagement.create.languageLabel")}
              options={languageProfiles.data ?? []}
              value={languageId}
              onChange={setLanguageId}
              disabled={submitting || !languageProfiles.isSuccess}
            />
            <ProfileSelect
              label={t("mediaManagement.create.namingLabel")}
              options={namingProfiles.data ?? []}
              value={namingId}
              onChange={setNamingId}
              disabled={submitting || !namingProfiles.isSuccess}
            />
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("mediaManagement.create.lifecycleLabel")}
              </span>
              <select
                value={lifecyclePolicy}
                onChange={(e) =>
                  setLifecyclePolicy(
                    e.target.value as LibraryLifecyclePolicy,
                  )
                }
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {_LIFECYCLE_POLICIES.map((option) => (
                  <option key={option} value={option}>
                    {t(`mediaManagement.create.lifecycleValue.${option}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("mediaManagement.create.flagsLabel")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("mediaManagement.create.flags.useHardlinks")}
              </span>
              <input
                type="checkbox"
                checked={useHardlinks}
                onChange={(e) => setUseHardlinks(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("mediaManagement.create.flags.monitoredDefault")}
              </span>
              <input
                type="checkbox"
                checked={monitoredDefault}
                onChange={(e) => setMonitoredDefault(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
          </fieldset>
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("mediaManagement.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? editing
                ? t("mediaManagement.edit.submitting")
                : t("mediaManagement.create.submitting")
              : editing
                ? t("mediaManagement.edit.submit")
                : t("mediaManagement.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}

interface ProfileSelectProps {
  label: string;
  options: ReadonlyArray<ProfileOption>;
  value: number | null;
  onChange: (next: number | null) => void;
  disabled: boolean;
}

function ProfileSelect(props: ProfileSelectProps): ReactElement {
  return (
    <label className="block">
      <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
        {props.label}
      </span>
      <select
        value={props.value === null ? "" : String(props.value)}
        onChange={(e) =>
          props.onChange(
            e.target.value === "" ? null : Number.parseInt(e.target.value, 10),
          )
        }
        disabled={props.disabled}
        className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
      >
        {props.options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}
