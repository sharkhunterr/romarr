/**
 * One row in the API-key audit list (slice 106).
 *
 * Shows the key prefix (first 8 chars), name, scopes, and the
 * created/last-used metadata. Plaintext was returned exactly
 * once at mint-time — the row only carries the prefix from then
 * on. Per-row delete is idempotent on the server.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteApiKey,
  type ApiKey,
} from "@/lib/api/queries/api-keys";

interface RowProps {
  apiKey: ApiKey;
}

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(locale);
}

export function ApiKeyRow(props: RowProps): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const { apiKey } = props;
  const del = useDeleteApiKey();
  const [confirming, setConfirming] = useState(false);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-zinc-100">
            {apiKey.name}
          </p>
          <p className="font-mono text-[0.65rem] text-zinc-500">
            {apiKey.key_prefix}…
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={[
            "shrink-0 rounded-md border border-red-900/50 px-3 py-1",
            "text-xs font-medium text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {t("general.apiKeys.revoke.button")}
        </button>
      </div>

      {apiKey.scopes.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {apiKey.scopes.map((scope) => (
            <span
              key={scope}
              className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-300"
            >
              {scope}
            </span>
          ))}
        </div>
      )}

      <p className="mt-2 text-[0.65rem] text-zinc-500">
        {t("general.apiKeys.timestamps", {
          created: formatDate(apiKey.created_at, i18n.language),
          lastUsed: apiKey.last_used_at
            ? formatDate(apiKey.last_used_at, i18n.language)
            : t("general.apiKeys.neverUsed"),
        })}
      </p>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("general.apiKeys.revoke.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("general.apiKeys.revoke.confirmBody", {
              name: apiKey.name,
            })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={() => del.mutate(apiKey.id)}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("general.apiKeys.revoke.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("general.apiKeys.revoke.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
