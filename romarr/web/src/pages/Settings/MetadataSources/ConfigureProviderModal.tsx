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

import { SecretInput } from "@/components/shared/SecretInput";
import {
  useMetadataProviderSecrets,
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
  /** Slice 407 — when true, the field renders under a
   * collapsed "Advanced" disclosure so the form stays one-
   * focal for the common case. */
  advanced?: boolean;
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
  // Slice 407 — ScreenScraper auth is RomM-style now: just
  // username + password. The dev credentials (``devid`` /
  // ``devpassword``) are optional and only matter if the
  // operator registered their own dev key on screenscraper.fr
  // (better rate-limit quota). The form renders the dev fields
  // collapsed under an Advanced section.
  screenscraper: [
    { key: "ssid", label: "Username", required: true },
    { key: "sspassword", label: "Password", secret: true, required: true },
    {
      key: "devid",
      label: "Developer ID (optional)",
      required: false,
      advanced: true,
    },
    {
      key: "devpassword",
      label: "Developer Password (optional)",
      secret: true,
      required: false,
      advanced: true,
    },
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
  const primaryFields = fields.filter((f) => !f.advanced);
  const advancedFields = fields.filter((f) => f.advanced);
  const noCreds = NO_CREDS_PROVIDERS.has(provider.provider_name);

  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Pull the decrypted config so the modal can pre-fill existing
  // credentials — no need to skip already-set fields anymore.
  // Skips the fetch entirely for no-creds providers.
  const secrets = useMetadataProviderSecrets(
    provider.provider_name,
    !noCreds,
  );

  useEffect(() => {
    // Reset when switching provider or when the secrets payload lands.
    // If no config is stored yet the fetch returns {}, so every field
    // starts blank as before.
    const stored = secrets.data ?? {};
    const seeded = Object.fromEntries(
      fields.map((f) => [f.key, String(stored[f.key] ?? "")]),
    );
    setValues(seeded);
    // Auto-expand the advanced disclosure when the operator has
    // populated a value in there — otherwise it's easy to think a
    // field is empty when it's just hidden behind the collapsed
    // details.
    if (advancedFields.some((f) => stored[f.key])) {
      setAdvancedOpen(true);
    }
  }, [provider.provider_name, secrets.data]);

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
            {/* Slice 408c — ScreenScraper note: Romarr ships
                the same community dev key as RomM / Skraper, so
                only the operator's personal ssid + sspassword
                are needed. Operators with their own registered
                dev key can paste it in the Advanced section to
                bypass the shared key's quota. */}
            {provider.provider_name === "screenscraper" && (
              <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-[0.7rem] text-zinc-400">
                {t("metadataSources.configure.ssDevKeyNote")}
              </div>
            )}
            {primaryFields.map((f) => (
              <label key={f.key} className="block text-xs text-zinc-400">
                <span className="mb-1 block">
                  {f.label}
                  {f.required && (
                    <span aria-hidden="true" className="ml-1 text-red-400">
                      *
                    </span>
                  )}
                </span>
                {f.secret ? (
                  <SecretInput
                    value={values[f.key] ?? ""}
                    onChange={(next) =>
                      setValues((prev) => ({ ...prev, [f.key]: next }))
                    }
                    placeholder={f.placeholder}
                    disabled={secrets.isPending}
                    ariaLabel={f.label}
                  />
                ) : (
                  <input
                    type="text"
                    autoComplete="off"
                    value={values[f.key] ?? ""}
                    placeholder={f.placeholder}
                    disabled={secrets.isPending}
                    onChange={(e) =>
                      setValues((prev) => ({
                        ...prev,
                        [f.key]: e.target.value,
                      }))
                    }
                    className={[
                      "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
                      "ring-1 ring-inset ring-zinc-700",
                      "focus-visible:outline-none focus-visible:ring-2",
                      "focus-visible:ring-brand",
                      "disabled:cursor-not-allowed disabled:opacity-60",
                    ].join(" ")}
                  />
                )}
              </label>
            ))}

            {advancedFields.length > 0 && (
              <details
                open={advancedOpen}
                onToggle={(e) =>
                  setAdvancedOpen((e.target as HTMLDetailsElement).open)
                }
                className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs"
              >
                <summary className="cursor-pointer select-none text-zinc-400 hover:text-zinc-200">
                  {t("metadataSources.configure.advanced")}
                </summary>
                <div className="mt-3 space-y-3">
                  {advancedFields.map((f) => (
                    <label key={f.key} className="block text-xs text-zinc-400">
                      <span className="mb-1 block">{f.label}</span>
                      {f.secret ? (
                        <SecretInput
                          value={values[f.key] ?? ""}
                          onChange={(next) =>
                            setValues((prev) => ({ ...prev, [f.key]: next }))
                          }
                          placeholder={f.placeholder}
                          disabled={secrets.isPending}
                          ariaLabel={f.label}
                        />
                      ) : (
                        <input
                          type="text"
                          autoComplete="off"
                          value={values[f.key] ?? ""}
                          placeholder={f.placeholder}
                          disabled={secrets.isPending}
                          onChange={(e) =>
                            setValues((prev) => ({
                              ...prev,
                              [f.key]: e.target.value,
                            }))
                          }
                          className={[
                            "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
                            "ring-1 ring-inset ring-zinc-700",
                            "focus-visible:outline-none focus-visible:ring-2",
                            "focus-visible:ring-brand",
                            "disabled:cursor-not-allowed disabled:opacity-60",
                          ].join(" ")}
                        />
                      )}
                    </label>
                  ))}
                </div>
              </details>
            )}

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
