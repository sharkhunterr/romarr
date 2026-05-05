/**
 * Per-provider credentials modal.
 *
 * Renders the right form for the provider's API contract:
 *   * igdb          → client_id + client_secret (Twitch OAuth)
 *   * screenscraper → devid + devpassword + ssid + sspassword
 *   * mobygames     → api_key
 *   * steamgriddb   → api_key
 *   * retroachievements → username + api_key
 *   * launchbox / howlongtobeat / hasheous / playmatch → no creds
 *
 * The form posts the resulting object to
 * ``PUT /api/v3/metadata/provider/{name}`` under the ``config``
 * key — the backend Fernet-encrypts it before persistence.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useTestMetadataProvider,
  useUpdateMetadataProvider,
  type MetadataProvider,
} from "@/lib/api/queries/metadata-sources";

interface FieldDef {
  key: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
  required?: boolean;
}

const FIELDS_BY_PROVIDER: Record<string, FieldDef[]> = {
  igdb: [
    { key: "client_id", label: "Twitch Client ID", required: true },
    {
      key: "client_secret",
      label: "Twitch Client Secret",
      secret: true,
      required: true,
    },
  ],
  screenscraper: [
    { key: "devid", label: "Developer ID", required: true },
    { key: "devpassword", label: "Developer Password", secret: true, required: true },
    { key: "ssid", label: "User Login", required: true },
    { key: "sspassword", label: "User Password", secret: true, required: true },
  ],
  mobygames: [
    { key: "api_key", label: "API Key", secret: true, required: true },
  ],
  steamgriddb: [
    { key: "api_key", label: "API Key", secret: true, required: true },
  ],
  retroachievements: [
    { key: "username", label: "Username", required: true },
    { key: "api_key", label: "Web API Key", secret: true, required: true },
  ],
};

const NO_CREDS_PROVIDERS = new Set([
  "launchbox",
  "howlongtobeat",
  "hasheous",
  "playmatch",
]);

interface ConfigureProviderModalProps {
  provider: MetadataProvider;
  onClose: () => void;
}

export function ConfigureProviderModal(
  props: ConfigureProviderModalProps,
): ReactElement {
  const { provider, onClose } = props;
  const { t } = useTranslation("settings");
  const update = useUpdateMetadataProvider();
  const test = useTestMetadataProvider();

  const fields = FIELDS_BY_PROVIDER[provider.provider_name] ?? [];
  const noCreds = NO_CREDS_PROVIDERS.has(provider.provider_name);

  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValues(Object.fromEntries(fields.map((f) => [f.key, ""])));
  }, [provider.provider_name]);

  function onSubmit(e: React.FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setError(null);

    const missing = fields
      .filter((f) => f.required && !values[f.key]?.trim())
      .map((f) => f.label);
    if (missing.length > 0) {
      setError(t("metadataSources.configure.required", { fields: missing.join(", ") }));
      return;
    }

    update.mutate(
      {
        providerName: provider.provider_name,
        payload: { config: values },
      },
      {
        onSuccess: () => {
          // Auto-fire a health probe so the operator gets the
          // green "live" badge immediately after saving valid
          // credentials, without an extra click on "Test".
          // Failures here just leave the badge in the
          // "untested/active" amber state — not blocking.
          test.mutate(provider.provider_name);
          onClose();
        },
        onError: (err) => setError(err.message),
      },
    );
  }

  const displayName = t(
    `metadataSources.providerName.${provider.provider_name}`,
    { defaultValue: provider.provider_name },
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="configure-provider-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-950 p-5 shadow-xl">
        <header className="mb-4">
          <h3
            id="configure-provider-title"
            className="text-base font-medium text-zinc-100"
          >
            {t("metadataSources.configure.title", { provider: displayName })}
          </h3>
          {!noCreds && (
            <p className="mt-1 text-xs text-zinc-500">
              {t("metadataSources.configure.subtitle")}
            </p>
          )}
        </header>

        {noCreds ? (
          <div className="space-y-4">
            <p className="text-sm text-zinc-400">
              {t("metadataSources.configure.noCreds")}
            </p>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="min-h-[36px] rounded-md border border-zinc-700 px-3 text-sm text-zinc-200 hover:bg-zinc-900"
              >
                {t("metadataSources.configure.close")}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            {fields.map((f) => (
              <label key={f.key} className="block text-xs text-zinc-400">
                <span className="mb-1 block">
                  {f.label}
                  {f.required && (
                    <span aria-hidden="true" className="ml-1 text-red-400">
                      *
                    </span>
                  )}
                </span>
                <input
                  type={f.secret ? "password" : "text"}
                  autoComplete={f.secret ? "new-password" : "off"}
                  value={values[f.key] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [f.key]: e.target.value }))
                  }
                  className={[
                    "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
                    "ring-1 ring-inset ring-zinc-700",
                    "focus-visible:outline-none focus-visible:ring-2",
                    "focus-visible:ring-brand",
                  ].join(" ")}
                />
              </label>
            ))}

            {error && (
              <p role="alert" className="text-xs text-red-400">
                {error}
              </p>
            )}

            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={update.isPending}
                className="min-h-[36px] rounded-md border border-zinc-700 px-3 text-sm text-zinc-200 hover:bg-zinc-900 disabled:opacity-60"
              >
                {t("metadataSources.configure.cancel")}
              </button>
              <button
                type="submit"
                disabled={update.isPending}
                className={[
                  "min-h-[36px] rounded-md border border-brand bg-brand",
                  "px-3 text-sm font-medium text-zinc-900 hover:bg-brand-300",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                ].join(" ")}
              >
                {update.isPending
                  ? t("metadataSources.configure.saving")
                  : t("metadataSources.configure.save")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
