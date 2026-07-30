/**
 * One row of the Update Center sources table.
 *
 * Actions column uses compact icon buttons with tooltips instead
 * of a stack of text pills — 7 wrapped labels ate the row height
 * and made the table unreadable on desktop AND mobile.
 */

import {
  Download,
  Eye,
  Pencil,
  Power,
  RefreshCw,
  ShieldCheck,
  Trash2,
  type LucideIcon,
} from "lucide-react";
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

import { EditCommunitySourceModal } from "./EditCommunitySourceModal";
import { PreviewModal } from "./PreviewModal";

interface Props {
  source: CommunitySource;
}

interface IconButtonProps {
  Icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "brand" | "amber" | "danger";
}

function IconButton(props: IconButtonProps): ReactElement {
  const { Icon, label, onClick, disabled = false, variant = "default" } = props;
  const base =
    "inline-flex h-7 w-7 items-center justify-center rounded border transition-colors disabled:cursor-not-allowed disabled:opacity-40";
  const themes = {
    default:
      "border-zinc-700 text-zinc-200 hover:bg-zinc-800 hover:text-zinc-100",
    brand:
      "border-brand/60 bg-brand/10 text-brand hover:bg-brand/20",
    amber:
      "border-amber-700/60 bg-amber-950/40 text-amber-200 hover:bg-amber-950/60",
    danger:
      "border-red-800/60 text-red-300 hover:bg-red-950/40",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`${base} ${themes[variant]}`}
    >
      <Icon size={14} aria-hidden="true" />
    </button>
  );
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
  const [editOpen, setEditOpen] = useState(false);

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
      <td className="px-3 py-2 align-top">
        <div className="flex items-center justify-end gap-1">
          <IconButton
            Icon={RefreshCw}
            label={t("updateCenter.check")}
            onClick={handleCheck}
            disabled={check.isPending}
          />
          <IconButton
            Icon={Eye}
            label={t("updateCenter.preview")}
            onClick={() => setPreviewOpen(true)}
          />
          <IconButton
            Icon={Pencil}
            label={t("updateCenter.edit")}
            onClick={() => setEditOpen(true)}
          />
          {source.trust_status === "pending" && (
            <IconButton
              Icon={ShieldCheck}
              label={t("updateCenter.trust")}
              onClick={handleTrust}
              disabled={patch.isPending}
              variant="amber"
            />
          )}
          <IconButton
            Icon={Download}
            label={
              source.trust_status === "pending"
                ? t("updateCenter.trustPendingHint")
                : t("updateCenter.apply")
            }
            onClick={handleApply}
            disabled={apply.isPending || source.trust_status === "pending"}
            variant="brand"
          />
          <IconButton
            Icon={Power}
            label={
              source.enabled
                ? t("updateCenter.disable")
                : t("updateCenter.enable")
            }
            onClick={handleToggleEnabled}
            disabled={patch.isPending}
          />
          <IconButton
            Icon={Trash2}
            label={t("updateCenter.delete")}
            onClick={handleDelete}
            disabled={del.isPending}
            variant="danger"
          />
        </div>
        {previewOpen && (
          <PreviewModal
            source={source}
            onClose={() => setPreviewOpen(false)}
          />
        )}
        {editOpen && (
          <EditCommunitySourceModal
            source={source}
            onClose={() => setEditOpen(false)}
          />
        )}
      </td>
    </tr>
  );
}
