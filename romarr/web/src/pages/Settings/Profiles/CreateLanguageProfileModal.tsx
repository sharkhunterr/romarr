/**
 * CreateLanguageProfileModal (slice 287).
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateLanguageProfile,
  type LanguageProfileCreate,
} from "@/lib/api/queries/language-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateLanguageProfileModalProps {
  onClose: () => void;
}

function _parseList(raw: string): string[] {
  return raw
    .split(/[,\n]/)
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);
}

export function CreateLanguageProfileModal(
  props: CreateLanguageProfileModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateLanguageProfile();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [requiredRaw, setRequiredRaw] = useState("");
  const [preferredRaw, setPreferredRaw] = useState("en");
  const [excludeJpOnly, setExcludeJpOnly] = useState(true);

  const requiredLanguages = useMemo(
    () => _parseList(requiredRaw),
    [requiredRaw],
  );
  const preferredLanguages = useMemo(
    () => _parseList(preferredRaw),
    [preferredRaw],
  );

  const submitting = create.isPending;
  const canSubmit = name.trim().length > 0;

  function commit(): void {
    if (!canSubmit) return;
    const payload: LanguageProfileCreate = {
      name: name.trim(),
      required_languages: requiredLanguages,
      preferred_languages: preferredLanguages,
      exclude_japanese_only: excludeJpOnly,
    };
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("profiles.language.create.successTitle"),
          description: t("profiles.language.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("profiles.language.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("profiles.language.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("profiles.language.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("profiles.language.create.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.language.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              disabled={submitting}
              placeholder={t("profiles.language.create.namePlaceholder")}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.language.create.requiredLabel")}
            </span>
            <textarea
              value={requiredRaw}
              onChange={(e) => setRequiredRaw(e.target.value)}
              rows={1}
              disabled={submitting}
              placeholder="en"
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("profiles.language.create.languageHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.language.create.preferredLabel")}
            </span>
            <textarea
              value={preferredRaw}
              onChange={(e) => setPreferredRaw(e.target.value)}
              rows={1}
              disabled={submitting}
              placeholder="en, fr"
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </label>

          <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
            <span className="text-xs text-zinc-300">
              {t("profiles.language.create.excludeJpOnly")}
            </span>
            <input
              type="checkbox"
              checked={excludeJpOnly}
              onChange={(e) => setExcludeJpOnly(e.target.checked)}
              disabled={submitting}
              className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
            />
          </label>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("profiles.language.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("profiles.language.create.submitting")
              : t("profiles.language.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
