/**
 * Preview modal — dry-run fetch of a source's manifest.
 *
 * Called before "Faire confiance" on a ``trust_status='pending'``
 * source so the operator can see what they're about to bring in;
 * also available on trusted sources via the "Aperçu" button as a
 * belt-and-suspenders check before an apply.
 *
 * Never mutates DB.
 */

import { useEffect, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  usePreviewCommunitySource,
  type CommunitySource,
} from "@/lib/api/queries/community";

interface Props {
  source: CommunitySource;
  onClose: () => void;
}

export function PreviewModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const { source } = props;
  const preview = usePreviewCommunitySource();

  useEffect(() => {
    preview.mutate(source.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.id]);

  const data = preview.data;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("updateCenter.previewModalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-lg flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.previewModalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {source.name} · {source.url}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          {preview.isPending && (
            <p className="text-xs text-zinc-500">
              {t("updateCenter.previewLoading")}
            </p>
          )}
          {preview.isError && (
            <p role="alert" className="text-xs text-red-400">
              {preview.error.message}
            </p>
          )}
          {data && data.error && (
            <div className="rounded border border-red-800/60 bg-red-950/30 p-2 text-xs text-red-300">
              {data.error}
            </div>
          )}
          {data && !data.error && (
            <>
              <div className="grid grid-cols-2 gap-2 rounded border border-zinc-800 bg-zinc-950/50 p-3 text-xs">
                <div>
                  <p className="text-[0.6rem] uppercase text-zinc-500">
                    {t("updateCenter.previewName")}
                  </p>
                  <p className="text-zinc-100">
                    {data.manifest_name ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[0.6rem] uppercase text-zinc-500">
                    {t("updateCenter.previewVersion")}
                  </p>
                  <p className="font-mono text-zinc-100">
                    {data.available_version ?? "—"}
                  </p>
                </div>
                <div className="col-span-2">
                  <p className="text-[0.6rem] uppercase text-zinc-500">
                    {t("updateCenter.previewDescription")}
                  </p>
                  <p className="text-zinc-300">
                    {data.manifest_description || "—"}
                  </p>
                </div>
              </div>
              <div>
                <p className="mb-1 text-[0.65rem] uppercase text-zinc-500">
                  {t("updateCenter.previewItems", {
                    count: data.item_count,
                  })}
                </p>
                <ul className="max-h-64 space-y-0.5 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/40 p-2 text-[0.7rem] text-zinc-300">
                  {data.items.length === 0 && (
                    <li className="italic text-zinc-500">
                      {t("updateCenter.previewNoItems")}
                    </li>
                  )}
                  {data.items.map((item, idx) => (
                    <li
                      key={`${item.path}-${idx}`}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="truncate font-mono">
                        {item.path}
                      </span>
                      {item.seed_key && (
                        <span className="shrink-0 rounded bg-zinc-800 px-1 text-[0.6rem] text-zinc-400">
                          {item.seed_key}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
          >
            {t("updateCenter.close")}
          </button>
        </footer>
      </div>
    </div>
  );
}
