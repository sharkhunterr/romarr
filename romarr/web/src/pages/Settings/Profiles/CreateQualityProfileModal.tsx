/**
 * CreateQualityProfileModal (slice 286).
 *
 * Single-step Add-new flow for the spec 006 Quality Profile.
 * Operator types a name + comma-separated ``allowed_formats``
 * (the canonical strings the operator's pack defines) + picks
 * which one is preferred + which is the upgrade ceiling.
 *
 * Cross-field validation enforced at submit:
 *   * preferred_format MUST be in allowed_formats;
 *   * upgrade_until_format MUST be in allowed_formats.
 *
 * Strings resolve through ``settings:profiles.quality.create.*``.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateQualityProfile,
  useUpdateQualityProfile,
  type QualityProfile,
  type QualityProfileCreate,
} from "@/lib/api/queries/quality-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateQualityProfileModalProps {
  onClose: () => void;
  // Slice 403 — when set, the modal is in edit mode: form
  // pre-fills from the profile, title swaps to "Edit", submit
  // fires PUT instead of POST.
  profile?: QualityProfile;
}

function _parseList(raw: string): string[] {
  return raw
    .split(/[,\n]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function CreateQualityProfileModal(
  props: CreateQualityProfileModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateQualityProfile();
  const update = useUpdateQualityProfile();
  const pushToast = useToastStore((s) => s.push);
  const editing = props.profile ?? null;

  const [name, setName] = useState(editing?.name ?? "");
  const [allowedFormatsRaw, setAllowedFormatsRaw] = useState(
    editing ? editing.allowed_formats.join(", ") : "cartridge, cd_chd",
  );
  const [preferredFormat, setPreferredFormat] = useState(
    editing?.preferred_format ?? "cartridge",
  );
  const [upgradeUntilFormat, setUpgradeUntilFormat] = useState(
    editing?.upgrade_until_format ?? "cartridge",
  );
  const [requireDatVerified, setRequireDatVerified] = useState(
    editing?.require_dat_verified ?? false,
  );
  const [allowArchive, setAllowArchive] = useState(
    editing?.allow_archive_double_compression ?? false,
  );
  // Operator-tunable floor for auto-grab (RSS sync + on-add).
  // 0 = grab anything with a positive pipeline score, anything
  // higher holds weak candidates back from auto-dispatch (they
  // still show in manual search).
  const [autoGrabMinScore, setAutoGrabMinScore] = useState<number>(
    editing?.auto_grab_min_score ?? 0,
  );

  const allowedFormats = useMemo(
    () => _parseList(allowedFormatsRaw),
    [allowedFormatsRaw],
  );

  const submitting = create.isPending || update.isPending;

  const validationError: string | null = (() => {
    if (name.trim().length === 0) return t("profiles.quality.create.errors.name");
    if (allowedFormats.length === 0)
      return t("profiles.quality.create.errors.allowedEmpty");
    if (!allowedFormats.includes(preferredFormat))
      return t("profiles.quality.create.errors.preferredNotAllowed");
    if (!allowedFormats.includes(upgradeUntilFormat))
      return t("profiles.quality.create.errors.upgradeNotAllowed");
    return null;
  })();
  const canSubmit = validationError === null;

  function commit(): void {
    if (!canSubmit) return;
    const payload: QualityProfileCreate = {
      name: name.trim(),
      allowed_formats: allowedFormats,
      preferred_format: preferredFormat,
      upgrade_until_format: upgradeUntilFormat,
      require_dat_verified: requireDatVerified,
      allow_archive_double_compression: allowArchive,
      auto_grab_min_score: Math.max(0, Math.floor(autoGrabMinScore || 0)),
    };
    const onError = (err: { message: string }) => {
      pushToast({
        kind: "error",
        title: editing
          ? t("profiles.quality.edit.errorTitle")
          : t("profiles.quality.create.errorTitle"),
        description: err.message,
      });
    };
    if (editing) {
      update.mutate(
        { id: editing.id, payload },
        {
          onSuccess: (saved) => {
            pushToast({
              kind: "success",
              title: t("profiles.quality.edit.successTitle"),
              description: t("profiles.quality.edit.successBody", {
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
          title: t("profiles.quality.create.successTitle"),
          description: t("profiles.quality.create.successBody", {
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
          ? t("profiles.quality.edit.modalTitle")
          : t("profiles.quality.create.modalTitle")
      }
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {editing
              ? t("profiles.quality.edit.modalTitle")
              : t("profiles.quality.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {editing
              ? t("profiles.quality.edit.subhead")
              : t("profiles.quality.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.quality.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("profiles.quality.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.quality.create.allowedFormatsLabel")}
            </span>
            <textarea
              value={allowedFormatsRaw}
              onChange={(e) => setAllowedFormatsRaw(e.target.value)}
              rows={2}
              disabled={submitting}
              placeholder="cartridge, cd_chd, cd_iso"
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("profiles.quality.create.allowedFormatsHint")}
            </p>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("profiles.quality.create.preferredLabel")}
              </span>
              <select
                value={preferredFormat}
                onChange={(e) => setPreferredFormat(e.target.value)}
                disabled={submitting || allowedFormats.length === 0}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {allowedFormats.length === 0 ? (
                  <option value="">—</option>
                ) : (
                  allowedFormats.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))
                )}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("profiles.quality.create.upgradeLabel")}
              </span>
              <select
                value={upgradeUntilFormat}
                onChange={(e) => setUpgradeUntilFormat(e.target.value)}
                disabled={submitting || allowedFormats.length === 0}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {allowedFormats.length === 0 ? (
                  <option value="">—</option>
                ) : (
                  allowedFormats.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))
                )}
              </select>
            </label>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.quality.create.flagsLabel")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("profiles.quality.create.flags.requireDat")}
              </span>
              <input
                type="checkbox"
                checked={requireDatVerified}
                onChange={(e) => setRequireDatVerified(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("profiles.quality.create.flags.allowArchive")}
              </span>
              <input
                type="checkbox"
                checked={allowArchive}
                onChange={(e) => setAllowArchive(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex flex-col gap-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="flex items-center justify-between gap-2">
                <span className="text-xs text-zinc-300">
                  {t("profiles.quality.create.flags.autoGrabMinScore")}
                </span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={autoGrabMinScore}
                  onChange={(e) =>
                    setAutoGrabMinScore(
                      Number.isFinite(e.target.valueAsNumber)
                        ? e.target.valueAsNumber
                        : 0,
                    )
                  }
                  disabled={submitting}
                  className="w-24 rounded-md bg-zinc-900 px-2 py-1 text-right text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                />
              </span>
              <span className="text-[0.65rem] text-zinc-500">
                {t("profiles.quality.create.flags.autoGrabMinScoreHint")}
              </span>
            </label>
          </fieldset>

          {validationError !== null && name.length > 0 && (
            <p
              role="status"
              className="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-1.5 text-[0.65rem] text-amber-200"
            >
              {validationError}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("profiles.quality.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? editing
                ? t("profiles.quality.edit.submitting")
                : t("profiles.quality.create.submitting")
              : editing
                ? t("profiles.quality.edit.submit")
                : t("profiles.quality.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
