/**
 * CreateDumpProfileModal (slice 287).
 *
 * Single-step Add-new flow for the spec 006 Dump Profile.
 * Operator types a name, picks the dump statuses to allow, and
 * toggles the four allow-* flags + a prefer-revision policy.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateDumpProfile,
  type DumpPreferRevision,
  type DumpProfileCreate,
} from "@/lib/api/queries/dump-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateDumpProfileModalProps {
  onClose: () => void;
}

const _DUMP_STATUSES: ReadonlyArray<string> = [
  "verified",
  "good",
  "proto",
  "beta",
  "demo",
  "sample",
];

const _PREFER_REVISIONS: ReadonlyArray<DumpPreferRevision> = [
  "latest",
  "earliest",
  "any",
];

function _parseList(raw: string): string[] {
  return raw
    .split(/[,\n]/)
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);
}

export function CreateDumpProfileModal(
  props: CreateDumpProfileModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateDumpProfile();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [allowedRaw, setAllowedRaw] = useState("verified, good");
  const [allowProtoBeta, setAllowProtoBeta] = useState(false);
  const [allowHacks, setAllowHacks] = useState(false);
  const [allowTrainers, setAllowTrainers] = useState(false);
  const [allowTranslations, setAllowTranslations] = useState(false);
  const [preferRevision, setPreferRevision] =
    useState<DumpPreferRevision>("latest");

  const allowedDumpStatus = useMemo(() => _parseList(allowedRaw), [allowedRaw]);
  const submitting = create.isPending;

  const validationError: string | null = (() => {
    if (name.trim().length === 0)
      return t("profiles.dump.create.errors.name");
    if (allowedDumpStatus.length === 0)
      return t("profiles.dump.create.errors.allowedEmpty");
    return null;
  })();
  const canSubmit = validationError === null;

  function commit(): void {
    if (!canSubmit) return;
    const payload: DumpProfileCreate = {
      name: name.trim(),
      allowed_dump_status: allowedDumpStatus,
      allow_proto_beta: allowProtoBeta,
      allow_hacks: allowHacks,
      allow_trainers: allowTrainers,
      allow_translations: allowTranslations,
      prefer_revision: preferRevision,
    };
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("profiles.dump.create.successTitle"),
          description: t("profiles.dump.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("profiles.dump.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("profiles.dump.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("profiles.dump.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("profiles.dump.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.dump.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              disabled={submitting}
              placeholder={t("profiles.dump.create.namePlaceholder")}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.dump.create.allowedLabel")}
            </span>
            <textarea
              value={allowedRaw}
              onChange={(e) => setAllowedRaw(e.target.value)}
              rows={2}
              disabled={submitting}
              placeholder={_DUMP_STATUSES.join(", ")}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("profiles.dump.create.allowedHint", {
                values: _DUMP_STATUSES.join(", "),
              })}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.dump.create.preferLabel")}
            </span>
            <select
              value={preferRevision}
              onChange={(e) =>
                setPreferRevision(e.target.value as DumpPreferRevision)
              }
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {_PREFER_REVISIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`profiles.dump.create.preferValue.${option}`)}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.dump.create.flagsLabel")}
            </legend>
            {(
              [
                ["protoBeta", allowProtoBeta, setAllowProtoBeta],
                ["hacks", allowHacks, setAllowHacks],
                ["trainers", allowTrainers, setAllowTrainers],
                ["translations", allowTranslations, setAllowTranslations],
              ] as ReadonlyArray<
                [string, boolean, (next: boolean) => void]
              >
            ).map(([key, checked, setter]) => (
              <label
                key={key}
                className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2"
              >
                <span className="text-xs text-zinc-300">
                  {t(`profiles.dump.create.flags.${key}`)}
                </span>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setter(e.target.checked)}
                  disabled={submitting}
                  className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
                />
              </label>
            ))}
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
            {t("profiles.dump.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("profiles.dump.create.submitting")
              : t("profiles.dump.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
