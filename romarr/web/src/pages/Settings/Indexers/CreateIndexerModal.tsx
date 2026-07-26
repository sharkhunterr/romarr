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

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { SecretInput } from "@/components/shared/SecretInput";
import {
  useCreateIndexer,
  useIndexerSecrets,
  useProbeIndexer,
  useUpdateIndexer,
  type Indexer,
  type IndexerCreate,
  type IndexerImplementation,
  type IndexerTestResult,
  type IndexerUpdate,
} from "@/lib/api/queries/indexers";
import { useToastStore } from "@/lib/store/toast";

interface CreateIndexerModalProps {
  onClose: () => void;
  /** Pre-fill from this row → modal switches to edit mode and
   * uses PUT instead of POST. Leaving the API key blank
   * preserves the existing key (the backend skips re-encrypt
   * when the field is omitted). */
  indexer?: Indexer | null;
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
  const update = useUpdateIndexer();
  const probe = useProbeIndexer();
  const pushToast = useToastStore((s) => s.push);

  const [probeResult, setProbeResult] = useState<IndexerTestResult | null>(
    null,
  );

  const editing = props.indexer ?? null;
  const isEdit = editing !== null;

  const [implementation, setImplementation] =
    useState<IndexerImplementation>(
      (editing?.implementation as IndexerImplementation | undefined) ??
        "torznab",
    );
  const [name, setName] = useState(editing?.name ?? "");
  const [url, setUrl] = useState(editing?.url ?? "");
  const [apiKey, setApiKey] = useState("");

  // In edit mode, pre-fill the api_key from the backend so operators
  // can see + tweak the existing value instead of typing "leave blank
  // to preserve" or guessing what's stored.
  const secrets = useIndexerSecrets(editing?.id, isEdit);
  useEffect(() => {
    if (isEdit && secrets.data?.api_key) {
      setApiKey(secrets.data.api_key);
    }
  }, [isEdit, secrets.data?.api_key]);
  const [enableRss, setEnableRss] = useState(editing?.enable_rss ?? true);
  const [enableAutomatic, setEnableAutomatic] = useState(
    editing?.enable_automatic_search ?? true,
  );
  const [enableInteractive, setEnableInteractive] = useState(
    editing?.enable_interactive_search ?? true,
  );
  const [timeoutSeconds, setTimeoutSeconds] = useState<number>(
    editing?.timeout_seconds ?? 30,
  );

  const submitting = create.isPending || update.isPending;
  const canSubmit =
    name.trim().length > 0 &&
    url.trim().length > 0 &&
    Number.isFinite(timeoutSeconds) &&
    timeoutSeconds >= 5 &&
    timeoutSeconds <= 600;

  function commit(): void {
    if (!canSubmit) return;
    if (isEdit && editing) {
      const payload: IndexerUpdate = {
        name: name.trim(),
        implementation,
        url: url.trim(),
        enable_rss: enableRss,
        enable_automatic_search: enableAutomatic,
        enable_interactive_search: enableInteractive,
        timeout_seconds: timeoutSeconds,
      };
      const trimmedKey = apiKey.trim();
      if (trimmedKey.length > 0) {
        // Only re-encrypt when the operator actually typed a new key.
        // Leaving the field blank preserves the existing one.
        (payload as IndexerUpdate & { api_key?: string | null }).api_key =
          trimmedKey;
      }
      update.mutate(
        { id: editing.id, payload },
        {
          onSuccess: (saved) => {
            pushToast({
              kind: "success",
              title: t("indexers.edit.successTitle"),
              description: t("indexers.edit.successBody", {
                name: saved.name,
              }),
            });
            props.onClose();
          },
          onError: (err) => {
            pushToast({
              kind: "error",
              title: t("indexers.edit.errorTitle"),
              description: err.message,
            });
          },
        },
      );
      return;
    }
    const payload: IndexerCreate = {
      name: name.trim(),
      implementation,
      url: url.trim(),
      api_key: apiKey.trim() || null,
      enabled: true,
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
      timeout_seconds: timeoutSeconds,
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
      aria-label={
        isEdit
          ? t("indexers.edit.modalTitle", { name: editing.name })
          : t("indexers.create.modalTitle")
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
            {isEdit
              ? t("indexers.edit.modalTitle", { name: editing.name })
              : t("indexers.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {isEdit
              ? t("indexers.edit.subhead")
              : t("indexers.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
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
              placeholder="http://prowlarr:9696/5"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.create.urlHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.apiKeyLabel")}
            </span>
            <SecretInput
              value={apiKey}
              onChange={setApiKey}
              placeholder={
                isEdit
                  ? t("indexers.edit.apiKeyPlaceholder")
                  : t("indexers.create.apiKeyPlaceholder")
              }
              disabled={submitting || (isEdit && secrets.isPending)}
              ariaLabel={t("indexers.create.apiKeyLabel")}
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {isEdit
                ? t("indexers.edit.apiKeyHint")
                : t("indexers.create.apiKeyHint")}
            </p>
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

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.create.timeoutLabel")}
            </span>
            <input
              type="number"
              min={5}
              max={600}
              step={5}
              value={timeoutSeconds}
              onChange={(e) =>
                setTimeoutSeconds(Number.parseInt(e.target.value, 10) || 0)
              }
              disabled={submitting}
              className="w-28 rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.create.timeoutHint")}
            </p>
          </label>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[0.65rem] text-zinc-500">
            {t("indexers.create.prowlarrHint")}
          </p>

          {probeResult !== null && (
            <div
              className={[
                "rounded-md border px-3 py-2 text-xs",
                probeResult.ok
                  ? "border-brand/40 bg-brand/10 text-brand"
                  : "border-red-900/60 bg-red-950/30 text-red-300",
              ].join(" ")}
            >
              {probeResult.ok
                ? `✓ ${t("indexers.test.successCaps")}${
                    probeResult.search_ok === true
                      ? ` · ${t("indexers.test.successSearch")}`
                      : ""
                  }`
                : `✗ ${
                    probeResult.message ??
                    t(
                      `indexers.health.${probeResult.category ?? "connectivity"}`,
                    )
                  }`}
            </div>
          )}
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={() => {
              if (!canSubmit) return;
              setProbeResult(null);
              probe.mutate(
                {
                  implementation,
                  url: url.trim(),
                  api_key: apiKey.trim() || null,
                },
                {
                  onSuccess: setProbeResult,
                  onError: (err) =>
                    setProbeResult({
                      ok: false,
                      caps_ok: false,
                      search_ok: null,
                      server: null,
                      category: "connectivity",
                      message: err.message,
                    }),
                },
              );
            }}
            disabled={!canSubmit || submitting || probe.isPending}
            className="mr-auto rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {probe.isPending
              ? t("indexers.test.running")
              : t("indexers.test.button")}
          </button>
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
              ? isEdit
                ? t("indexers.edit.submitting")
                : t("indexers.create.submitting")
              : isEdit
                ? t("indexers.edit.submit")
                : t("indexers.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
