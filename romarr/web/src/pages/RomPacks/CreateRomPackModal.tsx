/**
 * CreateRomPackModal (slices 461 + 463).
 *
 * Add or edit a ROM content pack. Two creation modes:
 *
 *   - **From URL** — a direct link to a ROM archive Romarr
 *     downloads itself.
 *   - **From indexer** — run a manual search, pick a result;
 *     it's dispatched to a download client and registered as a
 *     ``grab``-sourced pack. The watcher routes the completed
 *     download to the pack ingest pipeline.
 *
 * Edit mode is URL-only — a grab pack's source is fixed once
 * the download is in flight.
 *
 * The size cap is entered in GiB for sanity — the API stores
 * raw bytes.
 *
 * Strings resolve through ``settings:romPacks.modal.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/client";
import { usePlatforms } from "@/lib/api/queries/platforms";
import {
  useCreateRomPack,
  useGrabRomPack,
  useIngestRomPack,
  useUpdateRomPack,
  type RomPackRead,
} from "@/lib/api/queries/rom-packs";
import { useManualSearch, type Candidate } from "@/lib/api/queries/search";
import { useToastStore } from "@/lib/store/toast";

const _GIB = 1024 ** 3;
const _MIB = 1024 ** 2;

type CreateMode = "url" | "indexer";

interface ErrorDisplay {
  message: string;
  details: string | null;
}

function _extractError(err: ApiError): ErrorDisplay {
  const rawDetails = err.details as unknown;
  const details =
    typeof rawDetails === "string"
      ? rawDetails
      : rawDetails !== undefined && rawDetails !== null
        ? JSON.stringify(rawDetails)
        : null;
  return { message: err.message, details };
}

function _formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return "—";
  if (bytes >= _GIB) return `${(bytes / _GIB).toFixed(1)} GiB`;
  if (bytes >= _MIB) return `${(bytes / _MIB).toFixed(0)} MiB`;
  return `${bytes} B`;
}

interface CreateRomPackModalProps {
  onClose: () => void;
  editing?: RomPackRead | null;
}

export function CreateRomPackModal(
  props: CreateRomPackModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const platforms = usePlatforms();
  const create = useCreateRomPack();
  const update = useUpdateRomPack();
  const grab = useGrabRomPack();
  const ingest = useIngestRomPack();
  const search = useManualSearch();
  const pushToast = useToastStore((s) => s.push);

  const editing = props.editing ?? null;
  const isEdit = editing !== null;

  const [mode, setMode] = useState<CreateMode>("url");
  const [name, setName] = useState(editing?.name ?? "");
  const [url, setUrl] = useState(editing?.url ?? "");
  const [platformId, setPlatformId] = useState<number>(
    editing?.platform_id ?? 0,
  );
  const [maxGib, setMaxGib] = useState<string>(
    editing?.max_size_bytes != null
      ? String(editing.max_size_bytes / _GIB)
      : "",
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<ErrorDisplay | null>(null);

  const submitting =
    create.isPending || update.isPending || grab.isPending;
  const canSubmitUrl = name.trim().length > 0 && url.trim().length > 0;

  function _maxBytes(): number | null {
    const parsed = Number.parseFloat(maxGib);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.round(parsed * _GIB);
  }

  function _platformId(): number | null {
    return platformId > 0 ? platformId : null;
  }

  function commitUrl(): void {
    if (!canSubmitUrl) return;
    setError(null);
    const platform_id = _platformId();
    const max_size_bytes = _maxBytes();

    if (isEdit && editing !== null) {
      update.mutate(
        {
          id: editing.id,
          payload: { name: name.trim(), url: url.trim(), platform_id, max_size_bytes },
        },
        {
          onSuccess: () => {
            pushToast({
              kind: "success",
              title: t("romPacks.modal.toastUpdated", { name: name.trim() }),
            });
            props.onClose();
          },
          onError: (err) => setError(_extractError(err)),
        },
      );
    } else {
      create.mutate(
        { name: name.trim(), url: url.trim(), platform_id, max_size_bytes },
        {
          onSuccess: (created) => {
            // Kick the download off straight away — it streams
            // through the queue and shows in Activity, just like
            // a grab. No separate "Ingest" click needed.
            ingest.mutate(created.id);
            pushToast({
              kind: "success",
              title: t("romPacks.modal.toastCreated", { name: name.trim() }),
            });
            props.onClose();
          },
          onError: (err) => setError(_extractError(err)),
        },
      );
    }
  }

  function runSearch(): void {
    if (searchQuery.trim().length === 0) return;
    setError(null);
    search.mutate(
      {
        query: searchQuery.trim(),
        platformId: platformId > 0 ? platformId : undefined,
      },
      { onError: (err) => setError(_extractError(err)) },
    );
  }

  function grabCandidate(c: Candidate): void {
    if (name.trim().length === 0) {
      setError({
        message: t("romPacks.modal.nameRequiredForGrab"),
        details: null,
      });
      return;
    }
    setError(null);
    grab.mutate(
      {
        payload: {
          name: name.trim(),
          platform_id: _platformId(),
          max_size_bytes: _maxBytes(),
          indexer_id: c.indexer_id,
          indexer_guid: c.indexer_guid,
          download_url: c.download_url,
          title: c.title,
        },
      },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("romPacks.modal.toastGrabbed", { name: name.trim() }),
          });
          props.onClose();
        },
        onError: (err) => setError(_extractError(err)),
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={
        isEdit ? t("romPacks.modal.titleEdit") : t("romPacks.modal.titleAdd")
      }
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="flex max-h-[84vh] w-full max-w-lg flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {isEdit
              ? t("romPacks.modal.titleEdit")
              : t("romPacks.modal.titleAdd")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("romPacks.modal.subhead")}
          </p>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {!isEdit && (
            <div className="flex gap-1 rounded-md bg-zinc-950 p-0.5 ring-1 ring-inset ring-zinc-800">
              {(["url", "indexer"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={`flex-1 rounded px-2 py-1 text-[0.7rem] font-medium transition-colors ${
                    mode === m
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {t(`romPacks.modal.mode.${m}`)}
                </button>
              ))}
            </div>
          )}

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("romPacks.modal.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="No-Intro — Game Boy Advance"
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          {(isEdit || mode === "url") && (
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("romPacks.modal.urlLabel")}
              </span>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://archive.org/download/.../gba-romset.zip"
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              />
              <p className="mt-1 text-[0.65rem] text-zinc-500">
                {t("romPacks.modal.urlHint")}
              </p>
            </label>
          )}

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("romPacks.modal.platformLabel")}
            </span>
            <select
              value={platformId}
              onChange={(e) =>
                setPlatformId(Number.parseInt(e.target.value, 10) || 0)
              }
              disabled={submitting || platforms.isLoading}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value={0}>{t("romPacks.modal.platformAny")}</option>
              {platforms.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.slug})
                </option>
              ))}
            </select>
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("romPacks.modal.platformHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("romPacks.modal.maxSizeLabel")}
            </span>
            <input
              type="number"
              min="0"
              step="1"
              value={maxGib}
              onChange={(e) => setMaxGib(e.target.value)}
              placeholder="50"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("romPacks.modal.maxSizeHint")}
            </p>
          </label>

          {/* ---- Indexer search (create-only) ---------------------- */}
          {!isEdit && mode === "indexer" && (
            <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-950/40 p-2">
              <div className="flex gap-1">
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") runSearch();
                  }}
                  placeholder={t("romPacks.modal.searchPlaceholder")}
                  disabled={submitting}
                  className="min-w-0 flex-1 rounded-md bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                />
                <button
                  type="button"
                  onClick={runSearch}
                  disabled={
                    submitting ||
                    search.isPending ||
                    searchQuery.trim().length === 0
                  }
                  className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {search.isPending
                    ? t("romPacks.modal.searching")
                    : t("romPacks.modal.searchButton")}
                </button>
              </div>

              {search.isSuccess &&
                (search.data.candidates ?? []).length === 0 && (
                  <p className="text-[0.65rem] text-zinc-500">
                    {t("romPacks.modal.noResults")}
                  </p>
                )}
              {search.isSuccess &&
                (search.data.candidates ?? []).length > 0 && (
                <ul className="max-h-52 space-y-1 overflow-y-auto">
                  {(search.data.candidates ?? []).map((c, i) => (
                    <li key={`${c.indexer_id}-${c.indexer_guid}-${i}`}>
                      <button
                        type="button"
                        onClick={() => grabCandidate(c)}
                        disabled={submitting}
                        className="flex w-full flex-col gap-0.5 rounded border border-zinc-800 px-2 py-1.5 text-left hover:border-brand/50 hover:bg-brand/5 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <span className="truncate text-xs text-zinc-100">
                          {c.title}
                        </span>
                        <span className="font-mono text-[0.6rem] text-zinc-500">
                          {_formatBytes(c.size_bytes)}
                          {c.seeders != null
                            ? ` · ${c.seeders} ${t("romPacks.modal.seeders")}`
                            : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[0.6rem] text-zinc-600">
                {t("romPacks.modal.grabHint")}
              </p>
            </div>
          )}

          {error !== null && (
            <div className="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-[0.7rem] text-rose-200">
              <p className="font-semibold">
                {t("romPacks.modal.errorTitle")}
              </p>
              <p className="mt-0.5">{error.message}</p>
              {error.details !== null && (
                <p className="mt-1 font-mono text-[0.65rem] text-rose-300">
                  {error.details}
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
            {t("romPacks.modal.cancel")}
          </button>
          {/* Indexer mode commits per-result inside the list; only
              URL / edit mode has a footer submit. */}
          {(isEdit || mode === "url") && (
            <button
              type="button"
              onClick={commitUrl}
              disabled={!canSubmitUrl || submitting}
              className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting
                ? t("romPacks.modal.submitting")
                : isEdit
                  ? t("romPacks.modal.submitEdit")
                  : t("romPacks.modal.submitAdd")}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
