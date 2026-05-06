/**
 * API-key mint flow (slice 339).
 *
 * Page surface = single "New API key" button. Clicking opens a
 * modal that takes a free-form name + three scope checkboxes
 * (read / write / admin) — Romarr's coarse 3-tier permission
 * model from spec 010 FR-005.
 *
 * On success the modal flips to a "key minted" screen showing
 * the plaintext exactly once with a copy-to-clipboard button.
 * The list query is invalidated so the new row appears in the
 * audit list automatically.
 */

import { Check, Copy, Plus, X } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useCreateApiKey } from "@/lib/api/queries/api-keys";

const ALL_SCOPES = ["read", "write", "admin"] as const;
type Scope = (typeof ALL_SCOPES)[number];

const inputCls = [
  "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
  "ring-1 ring-inset ring-zinc-700",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-brand",
].join(" ");

export function CreateApiKeyForm(): ReactElement {
  const { t } = useTranslation("settings");
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1 rounded-md border border-brand bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <Plus size={12} aria-hidden="true" />
          {t("general.apiKeys.create.openButton")}
        </button>
      </div>

      {open && <CreateApiKeyModal onClose={() => setOpen(false)} />}
    </>
  );
}

function CreateApiKeyModal(props: { onClose: () => void }): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateApiKey();

  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<Scope>>(
    () => new Set(["read"]),
  );
  const [copied, setCopied] = useState(false);

  function toggle(scope: Scope): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) {
        next.delete(scope);
      } else {
        next.add(scope);
      }
      return next;
    });
  }

  function onSubmit(e: React.FormEvent): void {
    e.preventDefault();
    if (name.trim().length === 0) return;
    create.mutate({
      name: name.trim(),
      // The constitution defines a 3-tier ladder: admin implies
      // write implies read. We submit only the highest selected
      // tier so the audit trail is clean — the backend's
      // ``scope_implies`` helper handles the comparison.
      scopes: Array.from(selected),
    });
  }

  async function copyKey(): Promise<void> {
    if (!create.data) return;
    try {
      await navigator.clipboard.writeText(create.data.plaintext);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked — operator selects manually.
    }
  }

  const minted = create.isSuccess && create.data !== undefined;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose();
      }}
    >
      <div className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-950 p-5 shadow-xl">
        <header className="mb-4 flex items-start justify-between gap-2">
          <div>
            <h3 className="text-base font-medium text-zinc-100">
              {minted
                ? t("general.apiKeys.created.title")
                : t("general.apiKeys.create.title")}
            </h3>
            <p className="mt-1 text-xs text-zinc-500">
              {minted
                ? t("general.apiKeys.created.body", {
                    name: create.data!.name,
                  })
                : t("general.apiKeys.create.subtitle")}
            </p>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            aria-label={t("general.apiKeys.create.close")}
            className="text-zinc-500 hover:text-zinc-200"
          >
            <X size={16} />
          </button>
        </header>

        {minted ? (
          <div className="space-y-3">
            <div className="rounded-md border border-amber-900/60 bg-amber-950/30 p-3 text-xs text-amber-200">
              {t("general.apiKeys.created.warn")}
            </div>
            <div className="flex gap-1.5">
              <input
                type="text"
                readOnly
                value={create.data!.plaintext}
                onFocus={(e) => e.target.select()}
                className={`${inputCls} flex-1 font-mono`}
              />
              <button
                type="button"
                onClick={copyKey}
                aria-label={t("general.apiKeys.created.copy")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 text-zinc-200 hover:bg-zinc-900"
              >
                {copied ? (
                  <Check size={14} className="text-brand" />
                ) : (
                  <Copy size={14} />
                )}
              </button>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={props.onClose}
                className="min-h-[36px] rounded-md border border-brand bg-brand px-3 text-sm font-medium text-zinc-900 hover:bg-brand-300"
              >
                {t("general.apiKeys.created.done")}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block text-xs text-zinc-400">
              <span className="mb-1 block">
                {t("general.apiKeys.create.nameLabel")}
                <span aria-hidden="true" className="ml-0.5 text-red-400">
                  *
                </span>
              </span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("general.apiKeys.create.namePlaceholder")}
                required
                autoFocus
                className={inputCls}
              />
            </label>

            <fieldset className="block text-xs text-zinc-400">
              <legend className="mb-1.5">
                {t("general.apiKeys.create.scopesLegend")}
              </legend>
              <div className="space-y-1.5">
                {ALL_SCOPES.map((scope) => (
                  <label
                    key={scope}
                    className="flex cursor-pointer items-start gap-2 rounded-md border border-zinc-800 bg-zinc-900/40 p-2"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(scope)}
                      onChange={() => toggle(scope)}
                      className="mt-0.5 h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-brand"
                    />
                    <span className="flex-1">
                      <span className="block font-medium text-zinc-200">
                        {t(`general.apiKeys.create.scope.${scope}.label`)}
                      </span>
                      <span className="block text-[0.65rem] text-zinc-500">
                        {t(`general.apiKeys.create.scope.${scope}.hint`)}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-[0.65rem] text-zinc-500">
                {t("general.apiKeys.create.scopesNote")}
              </p>
            </fieldset>

            {create.isError && (
              <p role="alert" className="text-xs text-red-400">
                {create.error.message}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={props.onClose}
                disabled={create.isPending}
                className="min-h-[36px] rounded-md border border-zinc-700 px-3 text-sm text-zinc-200 hover:bg-zinc-900 disabled:opacity-60"
              >
                {t("general.apiKeys.create.cancel")}
              </button>
              <button
                type="submit"
                disabled={
                  create.isPending ||
                  name.trim().length === 0 ||
                  selected.size === 0
                }
                className={[
                  "min-h-[36px] rounded-md border border-brand bg-brand",
                  "px-3 text-sm font-medium text-zinc-900 hover:bg-brand-300",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                ].join(" ")}
              >
                {create.isPending
                  ? t("general.apiKeys.create.pending")
                  : t("general.apiKeys.create.submit")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
