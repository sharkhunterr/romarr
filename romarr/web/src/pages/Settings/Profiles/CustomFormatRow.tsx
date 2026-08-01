/**
 * One row in the Custom Formats list.
 *
 * Compact single-line-header layout : toggle + name + score chip
 * + origin badge + condition count on one line, icon-only actions
 * on the right. Conditions collapse by default (chevron toggle).
 */

import {
  ChevronDown,
  ChevronRight,
  ListChecks,
  Pencil,
  Trash2,
} from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteCustomFormat,
  useToggleCustomFormatEnabled,
  type CustomFormat,
} from "@/lib/api/queries/custom-formats";
import { useToastStore } from "@/lib/store/toast";

import { CustomFormatEditorModal } from "./CustomFormatEditorModal";

type Origin = "factory" | "community" | "user";

function detectOrigin(format: CustomFormat): Origin {
  if (format.source_id) return "community";
  if (format.is_factory_default) return "factory";
  return "user";
}

function OriginBadge(props: { format: CustomFormat }): ReactElement {
  const { t } = useTranslation("settings");
  const origin = detectOrigin(props.format);
  const base =
    "inline-flex shrink-0 items-center rounded px-1.5 py-px text-[0.6rem] uppercase tracking-wider";
  if (origin === "community") {
    return (
      <span
        className={`${base} border border-brand/40 bg-brand/10 text-brand`}
        title={t("customFormats.originCommunityTooltip", {
          name: props.format.source_name ?? "?",
        })}
      >
        {t("customFormats.originCommunity")}
        {props.format.source_name && (
          <span className="ml-1 font-normal normal-case tracking-normal text-brand/80">
            · {props.format.source_name}
          </span>
        )}
      </span>
    );
  }
  if (origin === "factory") {
    return (
      <span
        className={`${base} border border-zinc-700 bg-zinc-800/60 text-zinc-400`}
      >
        {t("customFormats.originFactory")}
      </span>
    );
  }
  return (
    <span
      className={`${base} border border-sky-800/60 bg-sky-950/40 text-sky-300`}
    >
      {t("customFormats.originUser")}
    </span>
  );
}

function ScoreChip(props: { score: number }): ReactElement {
  const tone =
    props.score > 0
      ? "bg-brand/20 text-brand"
      : props.score < 0
        ? "bg-red-950/40 text-red-400"
        : "bg-zinc-800 text-zinc-400";
  const sign = props.score > 0 ? "+" : "";
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-px font-mono text-[0.65rem] font-semibold tabular-nums ${tone}`}
    >
      {sign}
      {props.score}
    </span>
  );
}

function ConditionsList(props: {
  conditions: CustomFormat["conditions"];
}): ReactElement {
  if (props.conditions.length === 0) {
    return <p className="text-xs text-zinc-500">—</p>;
  }
  return (
    <ul className="space-y-1">
      {props.conditions.map((c, idx) => (
        <li
          key={idx}
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 font-mono text-[0.65rem] text-zinc-400"
        >
          {Object.entries(c)
            .filter(([k]) => k !== "type")
            .map(([k, v]) => (
              <span key={k} className="mr-3">
                <span className="text-zinc-600">{k}:</span>{" "}
                <span className="text-zinc-300">{String(v)}</span>
              </span>
            ))}
        </li>
      ))}
    </ul>
  );
}

interface IconButtonProps {
  icon: ReactElement;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "danger";
}

function IconButton(props: IconButtonProps): ReactElement {
  const { icon, label, onClick, disabled = false, variant = "default" } = props;
  const cls = variant === "danger"
    ? "border-red-900/50 text-red-400 hover:bg-red-950/40"
    : "border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${cls}`}
    >
      {icon}
    </button>
  );
}

interface CustomFormatRowProps {
  format: CustomFormat;
}

export function CustomFormatRow(props: CustomFormatRowProps): ReactElement {
  const { format } = props;
  const { t } = useTranslation("settings");
  const del = useDeleteCustomFormat();
  const toggle = useToggleCustomFormatEnabled();
  const pushToast = useToastStore((s) => s.push);

  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const enabled = format.enabled ?? true;

  function confirmDelete(): void {
    del.mutate(format.id);
  }

  function toggleEnabled(): void {
    toggle.mutate(
      { id: format.id, enabled: !enabled },
      {
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("customFormats.toggleErrorTitle"),
            description: err.message,
          }),
      },
    );
  }

  return (
    <li
      className={`rounded-md border border-zinc-800 bg-zinc-900/40 p-2 ${
        enabled ? "" : "opacity-60"
      }`}
    >
      <div className="flex items-center gap-2">
        {/* Toggle switch — click flips enabled */}
        <button
          type="button"
          onClick={toggleEnabled}
          disabled={toggle.isPending}
          role="switch"
          aria-checked={enabled}
          title={
            enabled
              ? t("customFormats.toggleDisableHint")
              : t("customFormats.toggleEnableHint")
          }
          className={[
            "inline-flex h-4 w-8 shrink-0 items-center rounded-full transition-colors",
            enabled ? "bg-brand" : "bg-zinc-700",
            "disabled:cursor-not-allowed disabled:opacity-50",
          ].join(" ")}
        >
          <span
            className={[
              "inline-block h-3 w-3 rounded-full bg-white transition-transform",
              enabled ? "translate-x-4" : "translate-x-0.5",
            ].join(" ")}
          />
        </button>

        {/* Expand chevron */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={t("customFormats.conditions")}
          title={t("customFormats.conditions")}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
        >
          {expanded ? (
            <ChevronDown size={14} aria-hidden="true" />
          ) : (
            <ChevronRight size={14} aria-hidden="true" />
          )}
        </button>

        {/* Title + score + count — the main info block */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-medium text-zinc-100">
              {format.name}
            </span>
            <ScoreChip score={format.score} />
            <span
              className="inline-flex shrink-0 items-center gap-0.5 rounded bg-zinc-800/60 px-1.5 py-px text-[0.65rem] text-zinc-400"
              title={t("customFormats.conditionsCount", {
                count: format.conditions.length,
              })}
            >
              <ListChecks size={11} aria-hidden="true" />
              <span className="tabular-nums">
                {format.conditions.length}
              </span>
            </span>
          </div>
        </div>

        {/* Action icons */}
        <IconButton
          icon={<Pencil size={13} strokeWidth={2.2} aria-hidden="true" />}
          label={t("customFormats.edit.button")}
          onClick={() => setEditOpen(true)}
        />
        <IconButton
          icon={<Trash2 size={13} strokeWidth={2.2} aria-hidden="true" />}
          label={
            format.is_factory_default
              ? t("customFormats.delete.factoryBlocked")
              : t("customFormats.delete.button")
          }
          onClick={() => setConfirming(true)}
          disabled={format.is_factory_default}
          variant="danger"
        />
      </div>

      {/* Origin + modified badges on their own line — compact, doesn't
          fight the title for horizontal space */}
      <div className="mt-1.5 flex flex-wrap items-center gap-1 pl-[52px]">
        <OriginBadge format={format} />
        {format.is_user_modified && (
          <span
            className="inline-flex shrink-0 items-center rounded border border-amber-800/50 bg-amber-950/40 px-1.5 py-px text-[0.6rem] uppercase tracking-wider text-amber-400"
            title={t("customFormats.modifiedTooltip")}
          >
            {t("customFormats.modified")}
          </span>
        )}
      </div>

      {expanded && (
        <div className="mt-2 pl-[52px]">
          <ConditionsList conditions={format.conditions} />
        </div>
      )}

      {editOpen && (
        <CustomFormatEditorModal
          format={format}
          onClose={() => setEditOpen(false)}
        />
      )}

      {confirming && (
        <div className="mt-2 rounded-md border border-red-900/50 bg-red-950/20 p-2.5">
          <p className="text-xs font-medium text-zinc-100">
            {t("customFormats.delete.confirmTitle")}
          </p>
          <p className="mt-0.5 text-[0.65rem] text-zinc-400">
            {t("customFormats.delete.confirmBody", { name: format.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className="rounded-md bg-red-600 px-2.5 py-1 text-[0.7rem] font-medium text-white hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("customFormats.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-md border border-zinc-700 px-2.5 py-1 text-[0.7rem] font-medium text-zinc-300 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {t("customFormats.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
