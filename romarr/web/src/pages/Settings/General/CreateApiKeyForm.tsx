/**
 * API-key mint form (slice 106).
 *
 * Single inline form: key name + comma-separated scope list.
 * On success the response carries the plaintext key — we
 * surface it exactly once in a callout the operator must
 * copy. The TanStack mutation invalidates the list query so
 * the new row lands in the audit list automatically.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useCreateApiKey } from "@/lib/api/queries/api-keys";

export function CreateApiKeyForm(): ReactElement {
  const { t } = useTranslation("settings");
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState("");
  const create = useCreateApiKey();

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (name.trim().length === 0) return;
    const scopeList = scopes
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    create.mutate(
      { name: name.trim(), scopes: scopeList },
      {
        onSuccess: () => {
          setName("");
          setScopes("");
        },
      },
    );
  };

  const onCopy = (): void => {
    if (!create.data) return;
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(create.data.plaintext);
    }
  };

  return (
    <div className="space-y-3">
      <form
        onSubmit={onSubmit}
        className={[
          "flex flex-col gap-2 rounded-md border border-zinc-800",
          "bg-zinc-900/40 p-3",
        ].join(" ")}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
          {t("general.apiKeys.create.title")}
        </h3>
        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.apiKeys.create.nameLabel")}
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("general.apiKeys.create.namePlaceholder")}
            required
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
        </label>
        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.apiKeys.create.scopesLabel")}
          </span>
          <input
            type="text"
            value={scopes}
            onChange={(e) => setScopes(e.target.value)}
            placeholder={t("general.apiKeys.create.scopesPlaceholder")}
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
          <span className="mt-1 block text-[0.65rem] text-zinc-500">
            {t("general.apiKeys.create.scopesHint")}
          </span>
        </label>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={create.isPending || name.trim().length === 0}
            className={[
              "rounded-md bg-brand/20 px-3 py-1.5 text-xs font-medium",
              "text-brand ring-1 ring-inset ring-brand/40",
              "hover:bg-brand/30",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {create.isPending
              ? t("general.apiKeys.create.pending")
              : t("general.apiKeys.create.submit")}
          </button>
        </div>
        {create.isError && (
          <p className="text-[0.7rem] text-red-300">{create.error.message}</p>
        )}
      </form>

      {create.isSuccess && create.data && (
        <div
          role="status"
          className={[
            "space-y-2 rounded-md border border-emerald-900/50",
            "bg-emerald-950/20 p-3",
          ].join(" ")}
        >
          <p className="text-sm font-medium text-emerald-200">
            {t("general.apiKeys.created.title")}
          </p>
          <p className="text-xs text-zinc-300">
            {t("general.apiKeys.created.body", { name: create.data.name })}
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-zinc-950 px-2 py-1 font-mono text-[0.7rem] text-zinc-100 ring-1 ring-inset ring-zinc-700">
              {create.data.plaintext}
            </code>
            <button
              type="button"
              onClick={onCopy}
              className={[
                "rounded-md border border-emerald-800 px-2.5 py-1",
                "text-[0.7rem] font-medium text-emerald-200",
                "hover:bg-emerald-950/40",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500",
              ].join(" ")}
            >
              {t("general.apiKeys.created.copy")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
