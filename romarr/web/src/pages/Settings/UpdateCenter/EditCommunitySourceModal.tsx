/**
 * Edit an existing community source — name + URL.
 *
 * Changing the URL resets last_seen_version / installed_version /
 * trust_status (backend enforces this) — the "URL change =
 * effectively a new source" invariant.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  usePatchCommunitySource,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

interface Props {
  source: CommunitySource;
  onClose: () => void;
}

export function EditCommunitySourceModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const patch = usePatchCommunitySource();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState(props.source.name);
  const [url, setUrl] = useState(props.source.url);

  const dirty =
    name.trim() !== props.source.name || url.trim() !== props.source.url;
  const urlChanged = url.trim() !== props.source.url;

  function submit(): void {
    if (!dirty || !name.trim() || !url.trim()) return;
    patch.mutate(
      {
        sourceId: props.source.id,
        name: name.trim() !== props.source.name ? name.trim() : undefined,
        url: urlChanged ? url.trim() : undefined,
      },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("updateCenter.editSuccessTitle"),
            description: urlChanged
              ? t("updateCenter.editUrlResetHint")
              : t("updateCenter.editSuccessBody", { name: name.trim() }),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("updateCenter.editErrorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("updateCenter.editModalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.editModalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("updateCenter.editModalHint")}
          </p>
        </header>

        <div className="space-y-4 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("updateCenter.addName")}
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("updateCenter.addUrl")}
            </span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            {urlChanged && (
              <p className="mt-1 rounded border border-amber-800/50 bg-amber-950/30 px-2 py-1 text-[0.65rem] text-amber-300">
                {t("updateCenter.editUrlWarning")}
              </p>
            )}
          </label>

          <p className="text-[0.65rem] text-zinc-500">
            <span className="text-zinc-400">
              {t("updateCenter.editReadOnlyType")}:
            </span>{" "}
            {t(`updateCenter.type.${props.source.resource_type}`, {
              defaultValue: props.source.resource_type,
            })}
          </p>

          {patch.isError && (
            <p role="alert" className="text-xs text-red-400">
              {patch.error.message}
            </p>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
          >
            {t("updateCenter.cancel")}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!dirty || !name.trim() || !url.trim() || patch.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {patch.isPending
              ? t("updateCenter.editSubmitting")
              : t("updateCenter.editSubmit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
