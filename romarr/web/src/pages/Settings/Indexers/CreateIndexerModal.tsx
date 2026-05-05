/**
 * CreateIndexerModal (slice 284).
 *
 * Single-step Add-new flow for the spec 004 indexer surface.
 * Operator picks the implementation (newznab / torznab), enters
 * a name + URL + API key, toggles which RSS / interactive /
 * automatic search modes the indexer participates in, and
 * submits a ``IndexerCreate`` payload to ``POST /api/v3/indexer``.
 *
 * The remaining ``IndexerCreate`` fields (categories, priority,
 * rate_limit, seed_ratio, …) inherit the documented schema
 * defaults so the form stays focused on the bare minimum for a
 * working indexer; full edit ships when Romarr accepts an edit
 * flow as a follow-up.
 *
 * The recommended UX is still Prowlarr push (constitution
 * Article VII); the manual form here is the fallback for
 * deployments without Prowlarr.
 *
 * Strings resolve through ``settings:indexers.create.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateIndexer,
  type IndexerCreate,
  type IndexerImplementation,
} from "@/lib/api/queries/indexers";
import { useToastStore } from "@/lib/store/toast";

interface CreateIndexerModalProps {
  onClose: () => void;
}

const _IMPLEMENTATIONS: ReadonlyArray<IndexerImplementation> = [
  "newznab",
  "torznab",
];

export function CreateIndexerModal(
  props: CreateIndexerModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateIndexer();
  const pushToast = useToastStore((s) => s.push);

  const [implementation, setImplementation] =
    useState<IndexerImplementation>("torznab");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [enableRss, setEnableRss] = useState(true);
  const [enableAutomatic, setEnableAutomatic] = useState(true);
  const [enableInteractive, setEnableInteractive] = useState(true);

  const submitting = create.isPending;
  const canSubmit =
    name.trim().length > 0 && url.trim().length > 0;

  function commit(): void {
    if (!canSubmit) return;
    const payload: IndexerCreate = {
      name: name.trim(),
      implementation,
      url: url.trim(),
      api_key: apiKey.trim() || null,
      enable_rss: enableRss,
      enable_automatic_search: enableAutomatic,
      enable_interactive_search: enableInteractive,
      // Schema defaults — explicit because Pydantic strict.
      categories: [],
      min_seeders: 1,
      priority: 25,
      priority_indexer: false,
      discount_only: false,
      rate_limit_seconds: 5,
      result_limit: 100,
      timeout_seconds: 30,
      source: "manual",
    } as IndexerCreate;
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("indexers.create.successTitle"),
          description: t("indexers.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("indexers.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("indexers.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("indexers.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("indexers.create.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.implementationLabel")}
            </span>
            <select
              value={implementation}
              onChange={(e) =>
                setImplementation(e.target.value as IndexerImplementation)
              }
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {_IMPLEMENTATIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.create.implementationHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("indexers.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.urlLabel")}
            </span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://prowlarr.local/12/api"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.apiKeyLabel")}
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={t("indexers.create.apiKeyPlaceholder")}
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.flagsLabel")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2">
              <span className="text-xs text-zinc-200">
                {t("indexers.create.flags.enableRss")}
              </span>
              <input
                type="checkbox"
                checked={enableRss}
                onChange={(e) => setEnableRss(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("indexers.create.flags.enableAutomatic")}
              </span>
              <input
                type="checkbox"
                checked={enableAutomatic}
                onChange={(e) => setEnableAutomatic(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("indexers.create.flags.enableInteractive")}
              </span>
              <input
                type="checkbox"
                checked={enableInteractive}
                onChange={(e) => setEnableInteractive(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
          </fieldset>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[0.65rem] text-zinc-500">
            {t("indexers.create.prowlarrHint")}
          </p>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("indexers.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("indexers.create.submitting")
              : t("indexers.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
