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
  const pushToast = useToastStore((s) => s.push);

  const qualityProfiles = useQualityProfiles();
  const regionProfiles = useRegionProfiles();
  const dumpProfiles = useDumpProfiles();
  const languageProfiles = useLanguageProfiles();
  const namingProfiles = useNamingProfiles();

  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [qualityId, setQualityId] = useState<number | null>(null);
  const [regionId, setRegionId] = useState<number | null>(null);
  const [dumpId, setDumpId] = useState<number | null>(null);
  const [languageId, setLanguageId] = useState<number | null>(null);
  const [namingId, setNamingId] = useState<number | null>(null);
  const [lifecyclePolicy, setLifecyclePolicy] =
    useState<LibraryLifecyclePolicy>("hardlink_and_seed");
  const [useHardlinks, setUseHardlinks] = useState(true);
  const [monitoredDefault, setMonitoredDefault] = useState(true);

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
      setNamingId(_profilePickFirst(namingProfiles.data));
    }
  }, [namingId, namingProfiles.data]);

  const submitting = create.isPending;
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
      onError: (err) => {
        // Backend envelope ships the precise reason in ``details``
        // (e.g. ``library.path 'X': could not create (Permission
        // denied)``). Fall through to the bare ``message`` only
        // when nothing more useful is on the row.
        const apiDetails =
          typeof err.details === "string"
            ? (err.details as string)
            : null;
        pushToast({
          kind: "error",
          title: t("mediaManagement.create.errorTitle"),
          description: apiDetails ?? err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("mediaManagement.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("mediaManagement.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("mediaManagement.create.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
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

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
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
              ? t("mediaManagement.create.submitting")
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
