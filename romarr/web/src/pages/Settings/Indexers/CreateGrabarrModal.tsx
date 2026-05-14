/**
 * CreateGrabarrModal (slice 428 / R3b).
 *
 * Atomic "Add Grabarr" wizard — operator enters one form and the
 * backend creates both the indexer row (implementation='grabarr')
 * and the linked download_client row (type='grabarr_direct') in
 * a single transaction. The backend probes ``/romarr/api/v1/health``
 * BEFORE persisting, so protocol_version mismatch / bad apikey /
 * unreachable Grabarr surface as inline errors here rather than
 * a half-formed config.
 *
 * Differs from the generic ``CreateIndexerModal`` in three ways:
 *
 * 1. Two rows are created, not one — visible to the operator as a
 *    Grabarr appearing in BOTH Settings → Indexers and Settings →
 *    Download Clients lists after submit.
 * 2. Fields are Grabarr-specific (base_url + profile_slug instead
 *    of the generic ``url``, optional ``download_root`` for the
 *    http_direct streamer).
 * 3. Connectivity check is the wizard's *gate*, not an opt-in
 *    Test button — Romarr refuses to persist on failure so the
 *    inline error display is the only failure surface.
 *
 * Strings resolve through ``settings:indexers.grabarr.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/client";
import {
  useCreateGrabarrIntegration,
  type GrabarrWizardRequest,
} from "@/lib/api/queries/indexers";
import { useToastStore } from "@/lib/store/toast";

interface CreateGrabarrModalProps {
  onClose: () => void;
}

interface ErrorDisplay {
  message: string;
  details: string | null;
  code: string | null;
}

function _extractError(err: ApiError): ErrorDisplay {
  // Backend envelopes errors as ``{errorMessage, errorCode,
  // details}``; ApiError surfaces them on its own fields. The
  // wizard endpoint uses a plain string for ``details`` (e.g.,
  // "base_url must be http:// or https://"); the typed schema
  // expects a Record but the parser is lossy, so we accept both.
  const rawDetails = err.details as unknown;
  const details =
    typeof rawDetails === "string"
      ? rawDetails
      : rawDetails !== undefined && rawDetails !== null
        ? JSON.stringify(rawDetails)
        : null;
  return {
    message: err.message,
    details,
    code: err.errorCode ?? null,
  };
}

export function CreateGrabarrModal(
  props: CreateGrabarrModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateGrabarrIntegration();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [profileSlug, setProfileSlug] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState<number>(60);
  const [downloadRoot, setDownloadRoot] = useState("");
  const [error, setError] = useState<ErrorDisplay | null>(null);

  const submitting = create.isPending;
  const canSubmit =
    name.trim().length > 0 &&
    baseUrl.trim().length > 0 &&
    profileSlug.trim().length > 0 &&
    apiKey.trim().length > 0 &&
    Number.isFinite(timeoutSeconds) &&
    timeoutSeconds >= 5 &&
    timeoutSeconds <= 600;

  function commit(): void {
    if (!canSubmit) return;
    setError(null);
    const payload: GrabarrWizardRequest = {
      name: name.trim(),
      base_url: baseUrl.trim(),
      profile_slug: profileSlug.trim(),
      api_key: apiKey.trim(),
      timeout_seconds: timeoutSeconds,
      download_root:
        downloadRoot.trim().length > 0 ? downloadRoot.trim() : null,
    };
    create.mutate(payload, {
      onSuccess: (res) => {
        pushToast({
          kind: "success",
          title: t("indexers.grabarr.toastSuccess", {
            name: res.indexer.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        setError(_extractError(err));
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("indexers.grabarr.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("indexers.grabarr.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("indexers.grabarr.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("indexers.grabarr.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.baseUrlLabel")}
            </span>
            <input
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://grabarr.lan:8081"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.grabarr.baseUrlHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.profileSlugLabel")}
            </span>
            <input
              type="text"
              value={profileSlug}
              onChange={(e) => setProfileSlug(e.target.value)}
              placeholder="roms_all"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.grabarr.profileSlugHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.apiKeyLabel")}
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.timeoutLabel")}
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
              {t("indexers.grabarr.timeoutHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("indexers.grabarr.downloadRootLabel")}
            </span>
            <input
              type="text"
              value={downloadRoot}
              onChange={(e) => setDownloadRoot(e.target.value)}
              placeholder="/downloads"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("indexers.grabarr.downloadRootHint")}
            </p>
          </label>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[0.65rem] text-zinc-500">
            {t("indexers.grabarr.connectivityHint")}
          </p>

          {error !== null && (
            <div className="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-[0.7rem] text-rose-200">
              <p className="font-semibold">
                {t("indexers.grabarr.errorTitle")}
              </p>
              <p className="mt-0.5">{error.message}</p>
              {error.details !== null && (
                <p className="mt-1 font-mono text-[0.65rem] text-rose-300">
                  {error.details}
                </p>
              )}
              {error.code !== null && (
                <p className="mt-1 text-[0.6rem] text-rose-400">
                  {t("indexers.grabarr.errorCode")}: {error.code}
                </p>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 bg-zinc-950/50 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("indexers.grabarr.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("indexers.grabarr.submitting")
              : t("indexers.grabarr.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
