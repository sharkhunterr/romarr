/**
 * CreateDatSourceModal (slice 444).
 *
 * Add or edit one ``dat_source`` row (URL + name + platform +
 * source authority). Operator can either:
 * - paste a direct-download URL for a Logiqx DAT (preferred —
 *   refresh runs httpx GET against it and ingests on success);
 * - edit an existing row's URL when the seeded landing-page URL
 *   doesn't return a parseable DAT (e.g., redump.org's captcha
 *   wall → swap to a direct mirror).
 *
 * Strings resolve through ``settings:datSources.modal.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/client";
import { usePlatforms } from "@/lib/api/queries/platforms";
import {
  useCreateDatSource,
  useUpdateDatSource,
  type DatAuthoritySource,
  type DatSourceRead,
} from "@/lib/api/queries/dat-sources";
import { useToastStore } from "@/lib/store/toast";

const _SOURCE_OPTIONS: ReadonlyArray<DatAuthoritySource> = [
  "no-intro",
  "redump",
  "tosec",
  "goodtools",
  "hasheous",
  "playmatch",
  "custom",
];

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

interface CreateDatSourceModalProps {
  onClose: () => void;
  editing?: DatSourceRead | null;
}

export function CreateDatSourceModal(
  props: CreateDatSourceModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const platforms = usePlatforms();
  const create = useCreateDatSource();
  const update = useUpdateDatSource();
  const pushToast = useToastStore((s) => s.push);

  const editing = props.editing ?? null;
  const isEdit = editing !== null;

  const [name, setName] = useState(editing?.name ?? "");
  const [url, setUrl] = useState(editing?.url ?? "");
  const [source, setSource] = useState<DatAuthoritySource>(
    editing?.source ?? "no-intro",
  );
  const [platformId, setPlatformId] = useState<number>(
    editing?.platform_id ?? 0,
  );
  const [enabled, setEnabled] = useState(editing?.enabled ?? true);
  const [error, setError] = useState<ErrorDisplay | null>(null);

  const submitting = create.isPending || update.isPending;
  const canSubmit =
    name.trim().length > 0 &&
    url.trim().length > 0 &&
    (isEdit || (Number.isFinite(platformId) && platformId > 0));

  function commit(): void {
    if (!canSubmit) return;
    setError(null);
    if (isEdit && editing !== null) {
      update.mutate(
        {
          id: editing.id,
          payload: {
            name: name.trim(),
            url: url.trim(),
            enabled,
          },
        },
        {
          onSuccess: () => {
            pushToast({
              kind: "success",
              title: t("datSources.modal.toastUpdated", { name: name.trim() }),
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
          source,
          platform_id: platformId,
          enabled,
        },
        {
          onSuccess: () => {
            pushToast({
              kind: "success",
              title: t("datSources.modal.toastCreated", { name: name.trim() }),
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
      aria-label={isEdit ? t("datSources.modal.titleEdit") : t("datSources.modal.titleAdd")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {isEdit ? t("datSources.modal.titleEdit") : t("datSources.modal.titleAdd")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("datSources.modal.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("datSources.modal.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Redump — Sony PlayStation"
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("datSources.modal.urlLabel")}
            </span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/path/to/no-intro-psx.dat"
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("datSources.modal.urlHint")}
            </p>
          </label>

          {!isEdit && (
            <>
              <label className="block">
                <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                  {t("datSources.modal.sourceLabel")}
                </span>
                <select
                  value={source}
                  onChange={(e) => setSource(e.target.value as DatAuthoritySource)}
                  disabled={submitting}
                  className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                >
                  {_SOURCE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                  {t("datSources.modal.platformLabel")}
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
                    {t("datSources.modal.platformPlaceholder")}
                  </option>
                  {platforms.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.slug})
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              disabled={submitting}
              className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-950 text-brand focus:ring-brand"
            />
            <span className="text-xs text-zinc-300">
              {t("datSources.modal.enabledLabel")}
            </span>
          </label>

          {error !== null && (
            <div className="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-[0.7rem] text-rose-200">
              <p className="font-semibold">{t("datSources.modal.errorTitle")}</p>
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
            {t("datSources.modal.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("datSources.modal.submitting")
              : isEdit
                ? t("datSources.modal.submitEdit")
                : t("datSources.modal.submitAdd")}
          </button>
        </footer>
      </div>
    </div>
  );
}
