/**
 * CreateNamingProfileModal (slice 287).
 *
 * Single-step Add-new flow for the spec 006 Naming Profile.
 * Operator types a name + picks a convention + edits the
 * Jinja template + toggles the 3 structural flags.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateNamingProfile,
  type NamingProfileCreate,
} from "@/lib/api/queries/naming-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateNamingProfileModalProps {
  onClose: () => void;
}

type NamingConvention = NamingProfileCreate["convention"];

const _CONVENTIONS: ReadonlyArray<NamingConvention> = [
  "no-intro",
  "redump",
  "tosec",
  "es-de",
  "romm",
  "custom",
];

const _DEFAULT_TEMPLATE =
  "{{ Game.Title }} ({{ Release.Region }}).{{ Dump.Extension }}";

export function CreateNamingProfileModal(
  props: CreateNamingProfileModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateNamingProfile();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [convention, setConvention] = useState<NamingConvention>("no-intro");
  const [template, setTemplate] = useState(_DEFAULT_TEMPLATE);
  const [platformSubfolder, setPlatformSubfolder] = useState(true);
  const [replaceIllegal, setReplaceIllegal] = useState(true);
  const [multiDiscSubfolder, setMultiDiscSubfolder] = useState(true);

  const submitting = create.isPending;
  const canSubmit =
    name.trim().length > 0 && template.trim().length > 0;

  function commit(): void {
    if (!canSubmit) return;
    const payload: NamingProfileCreate = {
      name: name.trim(),
      convention,
      template: template.trim(),
      platform_subfolder: platformSubfolder,
      replace_illegal_chars: replaceIllegal,
      multi_disc_subfolder: multiDiscSubfolder,
    };
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("profiles.naming.create.successTitle"),
          description: t("profiles.naming.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("profiles.naming.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("profiles.naming.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("profiles.naming.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("profiles.naming.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("profiles.naming.create.nameLabel")}
              </span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                disabled={submitting}
                placeholder={t("profiles.naming.create.namePlaceholder")}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("profiles.naming.create.conventionLabel")}
              </span>
              <select
                value={convention}
                onChange={(e) =>
                  setConvention(e.target.value as NamingConvention)
                }
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {_CONVENTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.naming.create.templateLabel")}
            </span>
            <textarea
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={3}
              disabled={submitting}
              placeholder={_DEFAULT_TEMPLATE}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("profiles.naming.create.templateHint")}
            </p>
          </label>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.naming.create.flagsLabel")}
            </legend>
            {(
              [
                ["platformSubfolder", platformSubfolder, setPlatformSubfolder],
                ["replaceIllegal", replaceIllegal, setReplaceIllegal],
                ["multiDiscSubfolder", multiDiscSubfolder, setMultiDiscSubfolder],
              ] as ReadonlyArray<[string, boolean, (next: boolean) => void]>
            ).map(([key, checked, setter]) => (
              <label
                key={key}
                className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2"
              >
                <span className="text-xs text-zinc-300">
                  {t(`profiles.naming.create.flags.${key}`)}
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
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("profiles.naming.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("profiles.naming.create.submitting")
              : t("profiles.naming.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
