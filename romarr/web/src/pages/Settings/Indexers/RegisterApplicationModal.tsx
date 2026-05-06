/**
 * Register a Prowlarr instance.
 *
 * The flow:
 *   1. Operator opens Prowlarr → Settings → General → Security and
 *      copies the API key (single string, no per-scope selection
 *      because Prowlarr's API key is all-or-nothing).
 *   2. Operator pastes URL + API key here, picks a sync level,
 *      submits.
 *   3. Romarr POSTs `/api/v3/applications`. The response carries a
 *      one-time `app_token`; the operator copies it into Prowlarr's
 *      "Applications → Romarr → Application Token" field so the
 *      reverse channel (Prowlarr push → Romarr) can authenticate.
 *
 * The token is shown EXACTLY ONCE — the modal stays open on the
 * post-submit confirmation screen so the operator copies it before
 * dismissing. After dismiss, retrieving the token requires
 * deleting + re-registering the app.
 */

import { Check, Copy, ExternalLink } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateApplication,
  type ApplicationCreateResult,
} from "@/lib/api/queries/applications";

interface RegisterApplicationModalProps {
  onClose: () => void;
}

export function RegisterApplicationModal(
  props: RegisterApplicationModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateApplication();

  const [name, setName] = useState("Prowlarr");
  const [url, setUrl] = useState("http://localhost:9696");
  const [apiKey, setApiKey] = useState("");
  const [syncLevel, setSyncLevel] = useState<
    "disabled" | "add_only" | "full_sync"
  >("full_sync");
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function onSubmit(e: React.FormEvent): void {
    e.preventDefault();
    create.mutate(
      {
        name: name.trim(),
        prowlarr_url: url.trim().replace(/\/+$/, ""),
        prowlarr_api_key: apiKey.trim(),
        sync_level: syncLevel,
      },
      {
        onSuccess: (result: ApplicationCreateResult) => {
          setToken(result.app_token);
        },
      },
    );
  }

  async function copyToken(): Promise<void> {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard write blocked (insecure context) — leave the
      // text visible so the operator can select it manually.
    }
  }

  const canSubmit =
    name.trim().length > 0 &&
    url.trim().length > 0 &&
    apiKey.trim().length > 0 &&
    !create.isPending;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-lg border border-zinc-800 bg-zinc-950 p-5 shadow-xl">
        <header className="mb-4">
          <h3 className="text-base font-medium text-zinc-100">
            {token === null
              ? t("indexers.applications.register.title")
              : t("indexers.applications.register.successTitle")}
          </h3>
          <p className="mt-1 text-xs text-zinc-500">
            {token === null
              ? t("indexers.applications.register.subtitle")
              : t("indexers.applications.register.successBody")}
          </p>
        </header>

        {token === null ? (
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-300">
              <p className="font-medium text-zinc-100">
                {t("indexers.applications.register.howTo.title")}
              </p>
              <ol className="mt-1.5 list-decimal space-y-0.5 pl-4 text-zinc-400">
                <li>
                  {t("indexers.applications.register.howTo.step1")}
                </li>
                <li>
                  {t("indexers.applications.register.howTo.step2")}
                </li>
                <li>
                  {t("indexers.applications.register.howTo.step3")}
                </li>
              </ol>
              {url && (
                <a
                  href={`${url.replace(/\/+$/, "")}/settings/general`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-[0.7rem] text-brand hover:underline"
                >
                  <ExternalLink size={11} aria-hidden="true" />
                  {t("indexers.applications.register.howTo.openLink")}
                </a>
              )}
            </div>

            <label className="block text-xs text-zinc-400">
              <span className="mb-1 block">
                {t("indexers.applications.register.field.name")}
              </span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={inputCls}
                required
              />
            </label>

            <label className="block text-xs text-zinc-400">
              <span className="mb-1 block">
                {t("indexers.applications.register.field.url")}
                <span className="text-red-400" aria-hidden="true">*</span>
              </span>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://localhost:9696"
                className={`${inputCls} font-mono`}
                required
              />
            </label>

            <label className="block text-xs text-zinc-400">
              <span className="mb-1 block">
                {t("indexers.applications.register.field.apiKey")}
                <span className="text-red-400" aria-hidden="true">*</span>
              </span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="new-password"
                placeholder="32-character hex key"
                className={`${inputCls} font-mono`}
                required
              />
              <span className="mt-1 block text-[0.65rem] text-zinc-500">
                {t("indexers.applications.register.field.apiKeyHint")}
              </span>
            </label>

            <fieldset className="block text-xs text-zinc-400">
              <legend className="mb-1">
                {t("indexers.applications.register.field.syncLevel")}
              </legend>
              <div className="space-y-1.5">
                {(
                  [
                    "full_sync",
                    "add_only",
                    "disabled",
                  ] as const
                ).map((level) => (
                  <label
                    key={level}
                    className="flex cursor-pointer items-start gap-2 rounded-md border border-zinc-800 bg-zinc-900/40 p-2"
                  >
                    <input
                      type="radio"
                      name="sync_level"
                      value={level}
                      checked={syncLevel === level}
                      onChange={() => setSyncLevel(level)}
                      className="mt-0.5 accent-brand"
                    />
                    <span className="flex-1">
                      <span className="block font-medium text-zinc-200">
                        {t(
                          `indexers.applications.register.syncLevel.${level}.label`,
                        )}
                      </span>
                      <span className="block text-[0.65rem] text-zinc-500">
                        {t(
                          `indexers.applications.register.syncLevel.${level}.hint`,
                        )}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {create.isError && (
              <p role="alert" className="text-xs text-red-400">
                {create.error.message}
              </p>
            )}

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={props.onClose}
                disabled={create.isPending}
                className="min-h-[36px] rounded-md border border-zinc-700 px-3 text-sm text-zinc-200 hover:bg-zinc-900 disabled:opacity-60"
              >
                {t("indexers.applications.register.cancel")}
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                className={[
                  "min-h-[36px] rounded-md border border-brand bg-brand",
                  "px-3 text-sm font-medium text-zinc-900 hover:bg-brand-300",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                ].join(" ")}
              >
                {create.isPending
                  ? t("indexers.applications.register.submitting")
                  : t("indexers.applications.register.submit")}
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border border-amber-900/60 bg-amber-950/30 p-3 text-xs text-amber-200">
              {t("indexers.applications.register.tokenWarn")}
            </div>

            <label className="block text-xs text-zinc-400">
              <span className="mb-1 block">
                {t("indexers.applications.register.tokenLabel")}
              </span>
              <div className="flex gap-1.5">
                <input
                  type="text"
                  readOnly
                  value={token}
                  onFocus={(e) => e.target.select()}
                  className={`${inputCls} flex-1 font-mono`}
                />
                <button
                  type="button"
                  onClick={copyToken}
                  aria-label={t("indexers.applications.register.copy")}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 text-zinc-200 hover:bg-zinc-900"
                >
                  {copied ? (
                    <Check size={14} className="text-brand" />
                  ) : (
                    <Copy size={14} />
                  )}
                </button>
              </div>
            </label>

            <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-300">
              <p className="font-medium text-zinc-100">
                {t("indexers.applications.register.afterTitle")}
              </p>
              <ol className="mt-1.5 list-decimal space-y-0.5 pl-4 text-zinc-400">
                <li>{t("indexers.applications.register.after.step1")}</li>
                <li>{t("indexers.applications.register.after.step2")}</li>
                <li>{t("indexers.applications.register.after.step3")}</li>
              </ol>
              <p className="mt-2 rounded-sm bg-amber-950/40 px-2 py-1 text-[0.65rem] text-amber-200">
                {t("indexers.applications.register.sonarrCompatNote")}
              </p>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={props.onClose}
                className={[
                  "min-h-[36px] rounded-md border border-brand bg-brand",
                  "px-3 text-sm font-medium text-zinc-900 hover:bg-brand-300",
                ].join(" ")}
              >
                {t("indexers.applications.register.done")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const inputCls = [
  "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
  "ring-1 ring-inset ring-zinc-700",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-brand",
].join(" ");
