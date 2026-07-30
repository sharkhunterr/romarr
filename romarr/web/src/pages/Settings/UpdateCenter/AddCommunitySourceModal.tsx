/**
 * Shared "Add community URL" modal — used both from the Update
 * Center page and from the per-page shortcuts (Platforms, Custom
 * Formats) with the ``prefilledResourceType`` prop.
 *
 * Flow: enter name + URL + resource_type → POST → backend runs
 * the first check → operator sees the manifest name/version/item
 * count. Trust starts ``pending``; the operator confirms with
 * "Trust + Apply" in the Update Center row.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateCommunitySource,
  type CommunityResourceType,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

interface Props {
  prefilledResourceType?: CommunityResourceType;
  onClose: () => void;
}

export function AddCommunitySourceModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateCommunitySource();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [resourceType, setResourceType] =
    useState<CommunityResourceType>(
      props.prefilledResourceType ?? "custom_format",
    );

  function submit(): void {
    if (!name.trim() || !url.trim()) return;
    create.mutate(
      { name: name.trim(), url: url.trim(), resourceType },
      {
        onSuccess: (res) => {
          if (res.error) {
            pushToast({
              kind: "warning",
              title: t("updateCenter.addWarnTitle"),
              description: res.error,
            });
          } else {
            pushToast({
              kind: "success",
              title: t("updateCenter.addSuccessTitle"),
              description: t("updateCenter.addSuccessBody", {
                name: res.manifest_name ?? name,
                version: res.available_version ?? "?",
                count: res.item_count,
              }),
            });
          }
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("updateCenter.addErrorTitle"),
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
      aria-label={t("updateCenter.addModalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.addModalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("updateCenter.addModalHint")}
          </p>
        </header>

        <div className="space-y-4 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("updateCenter.addResourceType")}
            </span>
            <select
              value={resourceType}
              disabled={props.prefilledResourceType !== undefined}
              onChange={(e) =>
                setResourceType(e.target.value as CommunityResourceType)
              }
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-70"
            >
              <option value="custom_format">
                {t("updateCenter.type.custom_format")}
              </option>
              <option value="platform_pack">
                {t("updateCenter.type.platform_pack")}
              </option>
            </select>
          </label>

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
              {t("updateCenter.addUrl")}
            </span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://raw.githubusercontent.com/…/manifest.json"
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("updateCenter.addUrlHint")}
            </p>
          </label>

          {create.isError && (
            <p role="alert" className="text-xs text-red-400">
              {create.error.message}
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
            disabled={!name.trim() || !url.trim() || create.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending
              ? t("updateCenter.addSubmitting")
              : t("updateCenter.addSubmit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
