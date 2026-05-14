/**
 * CreateRomPackModal (slice 461).
 *
 * Add or edit one URL-sourced ROM content pack: a name, the
 * archive URL, an optional platform pin, and an optional
 * per-pack size cap. Leaving the platform unset lets a
 * multi-platform archive scatter its ROMs by per-file hash at
 * ingest time.
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
  useUpdateRomPack,
  type RomPackRead,
} from "@/lib/api/queries/rom-packs";
import { useToastStore } from "@/lib/store/toast";

const _GIB = 1024 ** 3;

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
  const pushToast = useToastStore((s) => s.push);

  const editing = props.editing ?? null;
  const isEdit = editing !== null;

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
  const [error, setError] = useState<ErrorDisplay | null>(null);

  const submitting = create.isPending || update.isPending;
  const canSubmit = name.trim().length > 0 && url.trim().length > 0;

  function _maxBytes(): number | null {
    const parsed = Number.parseFloat(maxGib);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.round(parsed * _GIB);
  }

  function commit(): void {
    if (!canSubmit) return;
    setError(null);
    const platform_id = platformId > 0 ? platformId : null;
    const max_size_bytes = _maxBytes();

    if (isEdit && editing !== null) {
      update.mutate(
        {
          id: editing.id,
          payload: {
            name: name.trim(),
            url: url.trim(),
            platform_id,
            max_size_bytes,
          },
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
        {
          name: name.trim(),
          url: url.trim(),
          platform_id,
          max_size_bytes,
        },
        {
          onSuccess: () => {
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
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
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

        <div className="space-y-3 p-4">
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
              <option value={0}>
                {t("romPacks.modal.platformAny")}
              </option>
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
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("romPacks.modal.submitting")
              : isEdit
                ? t("romPacks.modal.submitEdit")
                : t("romPacks.modal.submitAdd")}
          </button>
        </footer>
      </div>
    </div>
  );
}
