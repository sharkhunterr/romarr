/**
 * One community source, rendered as a card.
 *
 * Card layout > table cells because a full URL + version diff +
 * status + 7 action icons never fit clean in a mobile row. The
 * card stacks : header (name + type badge + status pill) → URL
 * (shortened) → version chip → action bar.
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
import { shortenSourceUrl } from "./urlDisplay";

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
    "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-40";
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

  // Status pill — colour + label combined.
  const statusPill = ((): { text: string; cls: string } | null => {
    if (!source.last_status) {
      return {
        text: t("updateCenter.status.never"),
        cls: "border-zinc-700 bg-zinc-800/50 text-zinc-400",
      };
    }
    const label = t(`updateCenter.status.${source.last_status}`, {
      defaultValue: source.last_status,
    });
    if (source.last_status === "error") {
      return { text: label, cls: "border-red-800/60 bg-red-950/40 text-red-300" };
    }
    if (source.last_status === "partial") {
      return {
        text: label,
        cls: "border-amber-800/60 bg-amber-950/40 text-amber-300",
      };
    }
    return {
      text: label,
      cls: "border-emerald-800/50 bg-emerald-950/30 text-emerald-300",
    };
  })();

  // Version chip — three states: never applied, up to date, update available.
  const versionChip = ((): { content: ReactElement; cls: string } => {
    const installed = source.installed_version;
    const available = source.last_seen_version;
    if (!installed && !available) {
      return {
        content: <span>{t("updateCenter.versionNever")}</span>,
        cls: "border-zinc-700 bg-zinc-800/50 text-zinc-500",
      };
    }
    if (!installed && available) {
      return {
        content: (
          <>
            <span className="text-zinc-500">{t("updateCenter.versionNew")}</span>
            <span className="ml-1 font-mono font-semibold">{available}</span>
          </>
        ),
        cls: "border-amber-800/60 bg-amber-950/40 text-amber-300",
      };
    }
    if (source.update_available) {
      return {
        content: (
          <>
            <span className="font-mono text-zinc-400 line-through decoration-zinc-600">
              {installed}
            </span>
            <span className="mx-1 text-amber-400">→</span>
            <span className="font-mono font-semibold">{available}</span>
          </>
        ),
        cls: "border-amber-800/60 bg-amber-950/40 text-amber-300",
      };
    }
    return {
      content: <span className="font-mono">{installed}</span>,
      cls: "border-emerald-800/50 bg-emerald-950/30 text-emerald-300",
    };
  })();

  return (
    <div
      className={`rounded-md border border-zinc-800 bg-zinc-950/40 p-3 ${
        source.enabled ? "" : "opacity-60"
      }`}
    >
      {/* Header — name + type + status */}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-zinc-100">
            {source.name}
          </p>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="mt-0.5 block truncate text-[0.7rem] text-zinc-500 hover:text-zinc-300 hover:underline"
            title={source.url}
          >
            {shortenSourceUrl(source.url)}
          </a>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="rounded border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-300">
            {t(`updateCenter.type.${source.resource_type}`, {
              defaultValue: source.resource_type,
            })}
          </span>
          {source.trust_status === "pending" && (
            <span
              className="rounded border border-amber-700/60 bg-amber-950/40 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-amber-300"
              title={t("updateCenter.trustPendingHint")}
            >
              {t("updateCenter.trustPending")}
            </span>
          )}
          {statusPill && (
            <span
              className={`rounded border px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider ${statusPill.cls}`}
            >
              {statusPill.text}
            </span>
          )}
        </div>
      </div>

      {/* Body — version chip + last error if any */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded border px-2 py-0.5 text-[0.7rem] ${versionChip.cls}`}
          title={t("updateCenter.versionTooltip")}
        >
          {versionChip.content}
        </span>
      </div>

      {source.last_error && (
        <p className="mt-2 rounded border border-red-800/40 bg-red-950/20 px-2 py-1 text-[0.65rem] text-red-300">
          {source.last_error}
        </p>
      )}

      {/* Action bar — icon-only, wraps if needed */}
      <div className="mt-3 flex flex-wrap items-center gap-1">
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
        <span className="mx-1 h-4 w-px bg-zinc-800" aria-hidden="true" />
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
    </div>
  );
}
