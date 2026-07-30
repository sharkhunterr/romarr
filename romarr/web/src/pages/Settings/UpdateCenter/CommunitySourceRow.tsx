/**
 * One row of the Update Center sources table.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useApplyCommunitySource,
  useCheckCommunitySource,
  useDeleteCommunitySource,
  usePatchCommunitySource,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

import { PreviewModal } from "./PreviewModal";

interface Props {
  source: CommunitySource;
}

export function CommunitySourceRow(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const { source } = props;
  const check = useCheckCommunitySource();
  const apply = useApplyCommunitySource();
  const patch = usePatchCommunitySource();
  const del = useDeleteCommunitySource();
  const pushToast = useToastStore((s) => s.push);
  const [previewOpen, setPreviewOpen] = useState(false);

  function handleCheck(): void {
    check.mutate(source.id, {
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("updateCenter.checkErrorTitle"),
          description: err.message,
        }),
    });
  }

  function handleApply(): void {
    apply.mutate(source.id, {
      onSuccess: (res) => {
        if (res.error) {
          pushToast({
            kind: "error",
            title: t("updateCenter.applyErrorTitle"),
            description: res.error,
          });
          return;
        }
        pushToast({
          kind: "success",
          title: t("updateCenter.applySuccessTitle"),
          description: t("updateCenter.applySuccessBody", {
            name: source.name,
            count: res.applied_count,
          }),
        });
      },
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("updateCenter.applyErrorTitle"),
          description: err.message,
        }),
    });
  }

  function handleTrust(): void {
    patch.mutate({ sourceId: source.id, trustStatus: "trusted" });
  }

  function handleToggleEnabled(): void {
    patch.mutate({ sourceId: source.id, enabled: !source.enabled });
  }

  function handleDelete(): void {
    if (!window.confirm(t("updateCenter.deleteConfirm", { name: source.name }))) {
      return;
    }
    del.mutate(source.id, {
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("updateCenter.deleteErrorTitle"),
          description: err.message,
        }),
    });
  }

  const statusColor =
    source.last_status === "error"
      ? "text-red-400"
      : source.last_status === "partial"
        ? "text-amber-300"
        : source.last_status === "ok"
          ? "text-emerald-400"
          : "text-zinc-500";

  return (
    <tr className={source.enabled ? "" : "opacity-60"}>
      <td className="px-3 py-2 align-top">
        <p className="font-medium text-zinc-100">{source.name}</p>
        <p className="mt-0.5 truncate max-w-xs text-[0.65rem] text-zinc-500">
          {source.url}
        </p>
      </td>
      <td className="px-3 py-2 align-top text-[0.65rem] uppercase text-zinc-400">
        {t(`updateCenter.type.${source.resource_type}`, {
          defaultValue: source.resource_type,
        })}
        {source.trust_status === "pending" && (
          <span
            className="ml-1 rounded bg-amber-900/40 px-1 text-amber-300"
            title={t("updateCenter.trustPendingHint")}
          >
            {t("updateCenter.trustPending")}
          </span>
        )}
      </td>
      <td className={`px-3 py-2 align-top ${statusColor}`}>
        {source.last_status
          ? t(`updateCenter.status.${source.last_status}`, {
              defaultValue: source.last_status,
            })
          : t("updateCenter.status.never")}
        {source.last_error && (
          <p className="mt-0.5 max-w-xs truncate text-[0.65rem] text-red-400">
            {source.last_error}
          </p>
        )}
      </td>
      <td className="px-3 py-2 align-top text-zinc-300">
        <span className="text-zinc-500">
          {source.installed_version ?? "—"}
        </span>
        {" → "}
        <span
          className={
            source.update_available ? "font-semibold text-amber-300" : ""
          }
        >
          {source.last_seen_version ?? "—"}
        </span>
      </td>
      <td className="px-3 py-2 align-top text-right">
        <div className="inline-flex flex-wrap justify-end gap-1">
          <button
            type="button"
            onClick={handleCheck}
            disabled={check.isPending}
            className="rounded border border-zinc-700 px-2 py-0.5 text-[0.65rem] text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
          >
            {t("updateCenter.check")}
          </button>
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            className="rounded border border-zinc-700 px-2 py-0.5 text-[0.65rem] text-zinc-200 hover:bg-zinc-800"
          >
            {t("updateCenter.preview")}
          </button>
          {source.trust_status === "pending" && (
            <button
              type="button"
              onClick={handleTrust}
              disabled={patch.isPending}
              className="rounded border border-amber-700/60 bg-amber-950/40 px-2 py-0.5 text-[0.65rem] text-amber-200 hover:bg-amber-950/60"
            >
              {t("updateCenter.trust")}
            </button>
          )}
          <button
            type="button"
            onClick={handleApply}
            disabled={apply.isPending || source.trust_status === "pending"}
            className="rounded border border-brand/60 bg-brand/10 px-2 py-0.5 text-[0.65rem] text-brand hover:bg-brand/20 disabled:cursor-not-allowed disabled:opacity-50"
            title={
              source.trust_status === "pending"
                ? t("updateCenter.trustPendingHint")
                : undefined
            }
          >
            {t("updateCenter.apply")}
          </button>
          <button
            type="button"
            onClick={handleToggleEnabled}
            disabled={patch.isPending}
            className="rounded border border-zinc-700 px-2 py-0.5 text-[0.65rem] text-zinc-300 hover:bg-zinc-800"
          >
            {source.enabled
              ? t("updateCenter.disable")
              : t("updateCenter.enable")}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={del.isPending}
            className="rounded border border-red-800/60 px-2 py-0.5 text-[0.65rem] text-red-300 hover:bg-red-950/40 disabled:opacity-50"
          >
            {t("updateCenter.delete")}
          </button>
        </div>
        {previewOpen && (
          <PreviewModal
            source={source}
            onClose={() => setPreviewOpen(false)}
          />
        )}
      </td>
    </tr>
  );
}
