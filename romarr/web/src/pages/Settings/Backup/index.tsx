/**
 * Settings > Backup page.
 *
 * Export/import à la carte des ressources persistées (profils,
 * indexers, download clients, notifications, DAT sources, packs…).
 * Backend endpoints : `/api/v3/backup/{manifest,export,import}`.
 *
 * Export flow — checkboxes remplies depuis le manifest, toggle
 * include_secrets, download côté client via ObjectURL. Import flow —
 * upload JSON, preview de ce que le bundle contient, choix du mode
 * (upsert/merge/replace), affichage du bilan par ressource.
 *
 * Import est destructif en mode replace : confirmation explicite
 * dans le bouton final (« Replace and wipe » libellé rouge).
 */

import { useMemo, useRef, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { apiFetch, ApiError } from "@/lib/api/client";
import { useQuery } from "@tanstack/react-query";

type ImportMode = "upsert" | "merge" | "replace";

interface ManifestEntry {
  key: string;
  label: string;
  count: number;
  has_secrets: boolean;
}

interface Manifest {
  resources: ManifestEntry[];
}

interface Bundle {
  romarr_version: string;
  exported_at: string;
  include_secrets: boolean;
  resources: Record<string, unknown[]>;
}

interface ImportOutcome {
  key: string;
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
}

interface ImportResult {
  outcomes: ImportOutcome[];
}

export function BackupPage(): ReactElement {
  const { t } = useTranslation("settings");

  const manifestQuery = useQuery<Manifest, ApiError>({
    queryKey: ["backup", "manifest"],
    queryFn: () => apiFetch<Manifest>("/api/v3/backup/manifest"),
  });

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("backup.title", "Backup & Restore")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t(
            "backup.subtitle",
            "Export a JSON bundle of the resources you pick, then re-import it into any Romarr install.",
          )}
        </p>
      </header>

      {manifestQuery.isPending ? (
        <ListSkeleton rows={4} />
      ) : manifestQuery.isError ? (
        <EmptyState
          title={t("backup.loadError", "Couldn't load the backup manifest.")}
          description={manifestQuery.error.message}
        />
      ) : (
        <>
          <ExportPanel entries={manifestQuery.data.resources} />
          <ImportPanel entries={manifestQuery.data.resources} />
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Export
// --------------------------------------------------------------------------

function ExportPanel({ entries }: { entries: ManifestEntry[] }): ReactElement {
  const { t } = useTranslation("settings");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(entries.filter((e) => e.count > 0).map((e) => e.key)),
  );
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const anySecrets = useMemo(
    () =>
      entries.some((e) => e.has_secrets && selected.has(e.key) && e.count > 0),
    [entries, selected],
  );

  const toggle = (key: string): void => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAll = (): void =>
    setSelected(new Set(entries.filter((e) => e.count > 0).map((e) => e.key)));
  const selectNone = (): void => setSelected(new Set());

  const doExport = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const bundle = await apiFetch<Bundle>("/api/v3/backup/export", {
        method: "POST",
        json: {
          resources: [...selected],
          include_secrets: includeSecrets,
        },
      });
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      a.download = `romarr-backup-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-900/30 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-zinc-100">
          {t("backup.export.title", "Export")}
        </h3>
        <div className="flex gap-2 text-xs">
          <button
            type="button"
            onClick={selectAll}
            className="rounded px-2 py-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            {t("backup.selectAll", "Select all")}
          </button>
          <button
            type="button"
            onClick={selectNone}
            className="rounded px-2 py-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            {t("backup.selectNone", "Select none")}
          </button>
        </div>
      </div>

      <ul className="mb-3 grid grid-cols-1 gap-1 sm:grid-cols-2">
        {entries.map((entry) => (
          <li key={entry.key}>
            <label
              className={[
                "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm",
                "hover:bg-zinc-800/50",
                entry.count === 0 ? "opacity-50" : "",
              ].join(" ")}
            >
              <input
                type="checkbox"
                checked={selected.has(entry.key)}
                onChange={() => toggle(entry.key)}
                disabled={entry.count === 0}
                className="accent-brand"
              />
              <span className="flex-1 text-zinc-100">{entry.label}</span>
              {entry.has_secrets && (
                <span
                  title={t(
                    "backup.hasSecretsHint",
                    "Contains secrets (opt-in below).",
                  )}
                  className="rounded-sm bg-amber-900/40 px-1.5 py-0.5 text-[0.6rem] font-medium uppercase text-amber-300"
                >
                  {t("backup.secretsBadge", "secret")}
                </span>
              )}
              <span className="font-mono text-xs text-zinc-500">
                {entry.count}
              </span>
            </label>
          </li>
        ))}
      </ul>

      <label
        className={[
          "mb-3 flex items-start gap-2 rounded px-2 py-1.5 text-sm",
          anySecrets ? "bg-amber-900/10" : "",
        ].join(" ")}
      >
        <input
          type="checkbox"
          checked={includeSecrets}
          onChange={(e) => setIncludeSecrets(e.target.checked)}
          className="mt-1 accent-brand"
        />
        <span className="flex-1">
          <span className="block text-zinc-100">
            {t("backup.includeSecrets", "Include secrets in export")}
          </span>
          <span className="mt-0.5 block text-xs text-zinc-400">
            {t(
              "backup.includeSecretsHint",
              "Passwords, API keys, apprise URLs. Store the file safely — it holds full credentials.",
            )}
          </span>
        </span>
      </label>

      {error && (
        <p
          role="alert"
          className="mb-3 rounded border border-red-900/50 bg-red-950/40 p-2 text-xs text-red-200"
        >
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={doExport}
        disabled={busy || selected.size === 0}
        className={[
          "rounded-md bg-brand px-4 py-2 text-sm font-medium text-white",
          "hover:bg-brand-hover",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-50",
        ].join(" ")}
      >
        {busy
          ? t("backup.exporting", "Exporting…")
          : t("backup.exportButton", "Download bundle")}
      </button>
    </section>
  );
}

// --------------------------------------------------------------------------
// Import
// --------------------------------------------------------------------------

function ImportPanel({ entries }: { entries: ManifestEntry[] }): ReactElement {
  const { t } = useTranslation("settings");
  const fileRef = useRef<HTMLInputElement>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<ImportMode>("upsert");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const labelByKey = useMemo(
    () => Object.fromEntries(entries.map((e) => [e.key, e.label])),
    [entries],
  );

  const bundleKeys = useMemo(
    () => (bundle ? Object.keys(bundle.resources) : []),
    [bundle],
  );

  const onFile = async (file: File): Promise<void> => {
    setError(null);
    setResult(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Bundle;
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        typeof parsed.resources !== "object"
      ) {
        throw new Error("Not a valid Romarr bundle (missing `resources`).");
      }
      setBundle(parsed);
      setSelected(new Set(Object.keys(parsed.resources)));
    } catch (e) {
      setBundle(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const toggle = (key: string): void => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const doImport = async (): Promise<void> => {
    if (!bundle) return;
    if (
      mode === "replace" &&
      !window.confirm(
        t(
          "backup.import.confirmReplace",
          "REPLACE mode will DELETE every existing item in the selected resources before importing. Continue?",
        ),
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await apiFetch<ImportResult>("/api/v3/backup/import", {
        method: "POST",
        json: {
          bundle,
          resources: [...selected],
          mode,
        },
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="mb-3 text-sm font-medium text-zinc-100">
        {t("backup.import.title", "Import")}
      </h3>

      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void onFile(f);
        }}
        className="mb-3 block w-full text-sm text-zinc-400 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-sm file:text-zinc-100 hover:file:bg-zinc-700"
      />

      {error && (
        <p
          role="alert"
          className="mb-3 rounded border border-red-900/50 bg-red-950/40 p-2 text-xs text-red-200"
        >
          {error}
        </p>
      )}

      {bundle && (
        <>
          <div className="mb-3 rounded bg-zinc-900/60 px-3 py-2 text-xs text-zinc-400">
            <span className="mr-3">
              <span className="text-zinc-500">version:</span>{" "}
              <span className="font-mono text-zinc-100">
                {bundle.romarr_version}
              </span>
            </span>
            <span className="mr-3">
              <span className="text-zinc-500">exported:</span>{" "}
              <span className="font-mono text-zinc-100">
                {bundle.exported_at}
              </span>
            </span>
            <span>
              <span className="text-zinc-500">secrets:</span>{" "}
              <span
                className={
                  bundle.include_secrets ? "text-amber-300" : "text-zinc-100"
                }
              >
                {bundle.include_secrets ? "included" : "not included"}
              </span>
            </span>
          </div>

          <ul className="mb-3 grid grid-cols-1 gap-1 sm:grid-cols-2">
            {bundleKeys.map((key) => (
              <li key={key}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-zinc-800/50">
                  <input
                    type="checkbox"
                    checked={selected.has(key)}
                    onChange={() => toggle(key)}
                    className="accent-brand"
                  />
                  <span className="flex-1 text-zinc-100">
                    {labelByKey[key] ?? key}
                  </span>
                  <span className="font-mono text-xs text-zinc-500">
                    {bundle.resources[key]?.length ?? 0}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <fieldset className="mb-3">
            <legend className="mb-1 text-xs font-medium uppercase tracking-widest text-zinc-500">
              {t("backup.import.mode.label", "Import mode")}
            </legend>
            <div className="flex flex-col gap-1 text-sm sm:flex-row sm:gap-4">
              {(
                [
                  {
                    key: "upsert",
                    label: t(
                      "backup.import.mode.upsert",
                      "Upsert (add + update by name)",
                    ),
                  },
                  {
                    key: "merge",
                    label: t(
                      "backup.import.mode.merge",
                      "Merge (add-only, skip existing)",
                    ),
                  },
                  {
                    key: "replace",
                    label: t(
                      "backup.import.mode.replace",
                      "Replace (wipe + recreate — destructive)",
                    ),
                  },
                ] as const
              ).map((opt) => (
                <label
                  key={opt.key}
                  className="flex cursor-pointer items-center gap-2"
                >
                  <input
                    type="radio"
                    name="import-mode"
                    checked={mode === opt.key}
                    onChange={() => setMode(opt.key)}
                    className="accent-brand"
                  />
                  <span
                    className={
                      opt.key === "replace"
                        ? "text-red-300"
                        : "text-zinc-100"
                    }
                  >
                    {opt.label}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <button
            type="button"
            onClick={doImport}
            disabled={busy || selected.size === 0}
            className={[
              "rounded-md px-4 py-2 text-sm font-medium text-white",
              mode === "replace"
                ? "bg-red-700 hover:bg-red-600"
                : "bg-brand hover:bg-brand-hover",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-50",
            ].join(" ")}
          >
            {busy
              ? t("backup.importing", "Importing…")
              : mode === "replace"
                ? t(
                    "backup.import.buttonReplace",
                    "Replace and wipe",
                  )
                : t("backup.import.button", "Import selected")}
          </button>
        </>
      )}

      {result && (
        <div className="mt-4">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-widest text-zinc-500">
            {t("backup.import.results", "Results")}
          </h4>
          <ul className="space-y-2">
            {result.outcomes.map((o) => (
              <li
                key={o.key}
                className="rounded border border-zinc-800 bg-zinc-950/40 p-2"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
                  <span className="font-medium text-zinc-100">
                    {labelByKey[o.key] ?? o.key}
                  </span>
                  <span className="text-xs text-emerald-400">
                    +{o.created} new
                  </span>
                  <span className="text-xs text-sky-400">
                    ~{o.updated} updated
                  </span>
                  <span className="text-xs text-zinc-400">
                    {o.skipped} skipped
                  </span>
                </div>
                {o.errors.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-xs text-amber-300">
                    {o.errors.map((e, i) => (
                      <li key={i}>• {e}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
