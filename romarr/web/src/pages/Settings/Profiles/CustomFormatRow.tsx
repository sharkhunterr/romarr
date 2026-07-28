/**
 * One row in the Custom Formats list (slice 64).
 *
 * Read-only audit view: name + score chip + conditions count
 * + factory/modified pills + collapsible conditions list.
 * Delete is gated on `is_factory_default` — operators reset
 * those by re-running the seed migration. The visual condition
 * builder + create/update flow lands in a follow-up slice.
 */

import { Pencil } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteCustomFormat,
  type CustomFormat,
} from "@/lib/api/queries/custom-formats";

import { CustomFormatEditorModal } from "./CustomFormatEditorModal";

interface CustomFormatRowProps {
  format: CustomFormat;
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
      className={`rounded px-1.5 py-0.5 font-mono text-[0.65rem] font-medium ${tone}`}
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

export function CustomFormatRow(props: CustomFormatRowProps): ReactElement {
  const { format } = props;
  const { t } = useTranslation("settings");
  const del = useDeleteCustomFormat();

  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  function confirmDelete(): void {
    del.mutate(format.id);
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {format.name}
            </p>
            <ScoreChip score={format.score} />
            {format.is_factory_default && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
                {t("customFormats.factory")}
              </span>
            )}
            {format.is_user_modified && (
              <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-amber-400">
                {t("customFormats.modified")}
              </span>
            )}
          </div>
          <p className="text-[0.65rem] text-zinc-500">
            {t("customFormats.conditionsCount", {
              count: format.conditions.length,
            })}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {expanded ? "▾" : "▸"} {t("customFormats.conditions")}
        </button>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className={[
            "flex min-h-[36px] items-center gap-1 rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          <Pencil size={12} strokeWidth={2.2} aria-hidden="true" />
          {t("customFormats.edit.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={format.is_factory_default}
          title={
            format.is_factory_default
              ? t("customFormats.delete.factoryBlocked")
              : undefined
          }
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-40",
          ].join(" ")}
        >
          {t("customFormats.delete.button")}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
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
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("customFormats.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("customFormats.delete.confirmBody", { name: format.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("customFormats.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("customFormats.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
