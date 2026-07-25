/**
 * Panneau « Pack Sources » — CRUD + sync des sources GitHub.
 *
 * Slotté au dessus de la liste des packs sur la page Platforms.
 * Endpoint backend : `/api/v3/rom/platform-pack-source/*`.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch, ApiError } from "@/lib/api/client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface PackSource {
  id: number;
  name: string;
  url: string;
  kind: "raw" | "github_dir";
  enabled: boolean;
  last_synced_at: string | null;
  last_status: "ok" | "partial" | "error" | null;
  last_error: string | null;
  last_applied_count: number;
}

interface SyncItemOutcome {
  filename: string;
  source_url: string;
  outcome: "applied" | "skipped" | "failed";
  pack_version: string | null;
  error: string | null;
}

interface SyncResult {
  source_id: number;
  fetched_at: string;
  status: "ok" | "partial" | "error";
  items: SyncItemOutcome[];
  applied_count: number;
}

const QK = ["platform-pack-sources"] as const;
const API = "/api/v3/rom/platform-pack-source";

function StatusBadge({
  status,
}: {
  status: PackSource["last_status"];
}): ReactElement {
  if (!status)
    return (
      <span className="rounded-sm bg-zinc-800/60 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
        never
      </span>
    );
  const styles: Record<NonNullable<PackSource["last_status"]>, string> = {
    ok: "bg-emerald-900/40 text-emerald-300",
    partial: "bg-amber-900/40 text-amber-200",
    error: "bg-red-900/40 text-red-300",
  };
  return (
    <span
      className={`rounded-sm px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider ${styles[status]}`}
    >
      {status}
    </span>
  );
}

export function PackSourcesPanel(): ReactElement {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [syncResults, setSyncResults] = useState<Record<number, SyncResult>>(
    {},
  );

  const list = useQuery<PackSource[], ApiError>({
    queryKey: QK,
    queryFn: () => apiFetch<PackSource[]>(API),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; url: string }) =>
      apiFetch<PackSource>(API, { method: "POST", json: body }),
    onSuccess: () => {
      setName("");
      setUrl("");
      setAddError(null);
      void qc.invalidateQueries({ queryKey: QK });
    },
    onError: (e: Error) => setAddError(e.message),
  });

  const patchEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiFetch<PackSource>(`${API}/${id}`, {
        method: "PATCH",
        json: { enabled },
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: QK }),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`${API}/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: QK }),
  });

  const sync = useMutation({
    mutationFn: (id: number) =>
      apiFetch<SyncResult>(`${API}/${id}/sync`, { method: "POST" }),
    onSuccess: (data, id) => {
      setSyncResults((prev) => ({ ...prev, [id]: data }));
      void qc.invalidateQueries({ queryKey: QK });
      void qc.invalidateQueries({ queryKey: ["platform-packs"] });
      void qc.invalidateQueries({ queryKey: ["platforms"] });
    },
  });

  const submit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!name.trim() || !url.trim()) return;
    create.mutate({ name: name.trim(), url: url.trim() });
  };

  return (
    <section className="space-y-3">
      <header>
        <h3 className="text-sm font-medium text-zinc-100">
          {t("platforms.sources.heading", "Pack sources")}
        </h3>
        <p className="text-[0.65rem] text-zinc-500">
          {t(
            "platforms.sources.subhead",
            "GitHub URLs that ship platform-pack YAMLs. Point at a raw *.yaml or a repo directory.",
          )}
        </p>
      </header>

      <form
        onSubmit={submit}
        className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3"
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto]">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t(
              "platforms.sources.namePlaceholder",
              "e.g. Community",
            )}
            className="rounded-md bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/tree/main/packs"
            className="rounded-md bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
          <button
            type="submit"
            disabled={create.isPending || !name.trim() || !url.trim()}
            className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {create.isPending
              ? t("platforms.sources.adding", "Adding…")
              : t("platforms.sources.add", "Add source")}
          </button>
        </div>
        {addError && (
          <p role="alert" className="mt-2 text-xs text-red-300">
            {addError}
          </p>
        )}
      </form>

      {list.isPending && (
        <p className="text-xs text-zinc-500">
          {t("platforms.sources.loading", "Loading sources…")}
        </p>
      )}
      {list.isError && (
        <p role="alert" className="text-xs text-red-300">
          {list.error.message}
        </p>
      )}
      {list.isSuccess && list.data.length === 0 && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t(
            "platforms.sources.empty",
            "No source registered yet. Add one above — try https://github.com/romarr-community/packs/tree/main/packs.",
          )}
        </p>
      )}

      {list.isSuccess && list.data.length > 0 && (
        <ul className="space-y-2">
          {list.data.map((source) => {
            const result = syncResults[source.id];
            const isSyncing = sync.isPending && sync.variables === source.id;
            return (
              <li
                key={source.id}
                className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-sm font-medium text-zinc-100">
                    {source.name}
                  </span>
                  <span className="rounded-sm bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-400">
                    {source.kind === "github_dir" ? "dir" : "raw"}
                  </span>
                  <StatusBadge status={source.last_status} />
                  {!source.enabled && (
                    <span className="rounded-sm bg-zinc-800/60 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
                      disabled
                    </span>
                  )}
                  {source.last_synced_at && (
                    <span className="ml-auto font-mono text-[0.65rem] text-zinc-500">
                      {new Date(source.last_synced_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="mt-1 truncate font-mono text-xs text-zinc-400">
                  {source.url}
                </div>
                {source.last_error && (
                  <p className="mt-2 rounded border border-red-900/40 bg-red-950/30 p-2 text-xs text-red-200">
                    {source.last_error}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={!source.enabled || isSyncing}
                    onClick={() => sync.mutate(source.id)}
                    className="rounded-md bg-brand px-3 py-1 text-xs font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isSyncing
                      ? t("platforms.sources.syncing", "Syncing…")
                      : t("platforms.sources.sync", "Sync now")}
                  </button>
                  <button
                    type="button"
                    disabled={patchEnabled.isPending}
                    onClick={() =>
                      patchEnabled.mutate({
                        id: source.id,
                        enabled: !source.enabled,
                      })
                    }
                    className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
                  >
                    {source.enabled
                      ? t("platforms.sources.disable", "Disable")
                      : t("platforms.sources.enable", "Enable")}
                  </button>
                  <button
                    type="button"
                    disabled={remove.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          t(
                            "platforms.sources.confirmDelete",
                            `Remove source "${source.name}"? Packs already applied stay in place.`,
                          ),
                        )
                      ) {
                        remove.mutate(source.id);
                      }
                    }}
                    className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-red-300 hover:bg-red-900/40 disabled:opacity-50"
                  >
                    {t("platforms.sources.delete", "Delete")}
                  </button>
                </div>
                {result && (
                  <div className="mt-3">
                    <p className="mb-1 font-mono text-[0.65rem] uppercase tracking-widest text-zinc-500">
                      {t("platforms.sources.lastRun", "Last sync")} —{" "}
                      {result.applied_count}{" "}
                      {t("platforms.sources.applied", "applied")} /{" "}
                      {result.items.length}{" "}
                      {t("platforms.sources.total", "total")}
                    </p>
                    <ul className="space-y-0.5 text-xs">
                      {result.items.map((item, i) => (
                        <li
                          key={`${item.filename}-${i}`}
                          className="flex items-baseline gap-2"
                        >
                          <span
                            className={
                              item.outcome === "applied"
                                ? "text-emerald-400"
                                : item.outcome === "failed"
                                  ? "text-red-300"
                                  : "text-zinc-500"
                            }
                          >
                            {item.outcome}
                          </span>
                          <span className="truncate font-mono text-zinc-300">
                            {item.filename}
                          </span>
                          {item.pack_version && (
                            <span className="ml-auto font-mono text-[0.65rem] text-zinc-500">
                              {item.pack_version}
                            </span>
                          )}
                          {item.error && (
                            <span className="text-[0.7rem] text-amber-300">
                              {item.error}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
