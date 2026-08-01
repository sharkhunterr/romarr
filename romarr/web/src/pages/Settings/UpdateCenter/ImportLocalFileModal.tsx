/**
 * Local (offline) pack import modal.
 *
 * Two file shapes accepted server-side :
 *   * ``.json``  — manifest with an ``inline_items`` array carrying full
 *                  bodies. Ideal for the air-gap case where one file
 *                  is easier to move than a folder tree.
 *   * ``.zip``   — ``manifest.json`` at the archive root plus item
 *                  files. Same layout as the community GitHub repo.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useImportCommunitySource } from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

interface Props {
  onClose: () => void;
}

export function ImportLocalFileModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const importSource = useImportCommunitySource();
  const pushToast = useToastStore((s) => s.push);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState<string>("");

  function submit(): void {
    if (!file || !name.trim()) return;
    importSource.mutate(
      { file, name: name.trim() },
      {
        onSuccess: (res) => {
          if (res.error) {
            pushToast({
              kind: "warning",
              title: t("updateCenter.importWarnTitle"),
              description: res.error,
            });
          } else {
            pushToast({
              kind: "success",
              title: t("updateCenter.importSuccessTitle"),
              description: t("updateCenter.importSuccessBody", {
                name: name.trim(),
                count: res.applied_count,
              }),
            });
          }
          props.onClose();
        },
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("updateCenter.importErrorTitle"),
            description: err.message,
          }),
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("updateCenter.importModalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-950/70 px-4 py-[4vh] backdrop-blur-sm sm:items-center"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.importModalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("updateCenter.importModalHint")}
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
              placeholder={t("updateCenter.addNamePlaceholder")}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("updateCenter.importFile")}
            </span>
            <input
              type="file"
              accept=".json,.zip,application/json,application/zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full text-xs text-zinc-300 file:mr-2 file:rounded file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-xs file:text-zinc-100 hover:file:bg-zinc-700"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("updateCenter.importFileHint")}
            </p>
          </label>

          {importSource.isError && (
            <p role="alert" className="text-xs text-red-400">
              {importSource.error.message}
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
            disabled={!file || !name.trim() || importSource.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {importSource.isPending
              ? t("updateCenter.importSubmitting")
              : t("updateCenter.importSubmit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
