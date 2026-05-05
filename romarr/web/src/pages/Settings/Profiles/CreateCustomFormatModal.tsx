/**
 * CreateCustomFormatModal — visual builder for Custom Formats
 * (spec 014 T097).
 *
 * The visual builder lets the operator compose a Custom Format
 * out of conditions without hand-rolling the JSON shape. v1
 * supports a flat condition list (no OR groups); operators that
 * need OR-grouped conditions today drop into the JSON-edit
 * surface (deferred to a follow-up slice).
 *
 * Per-condition layout: field dropdown + operator dropdown +
 * value input. The operator dropdown's options are filtered
 * contextually so e.g. ``release_size`` only offers numeric
 * comparisons. The value input is text by default; numeric
 * comparisons use ``type="number"`` and list operators (``in``
 * / ``not_in``) accept comma-separated entries.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateCustomFormat,
  type CustomFormatConditionInput,
  type CustomFormatField,
  type CustomFormatOperator,
} from "@/lib/api/queries/custom-formats";
import { useToastStore } from "@/lib/store/toast";

interface CreateCustomFormatModalProps {
  onClose: () => void;
}

const _FIELDS: ReadonlyArray<CustomFormatField> = [
  "tags",
  "region",
  "format",
  "dump_status",
  "release_group",
  "indexer_source",
  "languages",
  "revision",
  "naming_convention",
  "release_size",
];

const _STRING_OPERATORS: ReadonlyArray<CustomFormatOperator> = [
  "equals",
  "matches_regex",
  "contains",
  "in",
  "not_in",
];

const _NUMERIC_OPERATORS: ReadonlyArray<CustomFormatOperator> = [
  "greater_than",
  "less_than",
  "equals",
];

function _operatorsFor(field: CustomFormatField): readonly CustomFormatOperator[] {
  return field === "release_size" ? _NUMERIC_OPERATORS : _STRING_OPERATORS;
}

interface DraftCondition {
  field: CustomFormatField;
  operator: CustomFormatOperator;
  raw: string;
}

function _emptyCondition(): DraftCondition {
  return { field: "tags", operator: "equals", raw: "" };
}

function _projectCondition(
  draft: DraftCondition,
): CustomFormatConditionInput | null {
  const value = draft.raw.trim();
  if (!value) {
    return null;
  }
  if (draft.operator === "in" || draft.operator === "not_in") {
    const parts = value
      .split(/[,;\n]/)
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
    if (parts.length === 0) {
      return null;
    }
    return { field: draft.field, operator: draft.operator, values: parts };
  }
  if (draft.field === "release_size") {
    const num = Number(value);
    if (Number.isNaN(num)) {
      return null;
    }
    return { field: draft.field, operator: draft.operator, values: num };
  }
  return { field: draft.field, operator: draft.operator, values: value };
}

export function CreateCustomFormatModal(
  props: CreateCustomFormatModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateCustomFormat();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [scoreText, setScoreText] = useState("0");
  const [conditions, setConditions] = useState<DraftCondition[]>([
    _emptyCondition(),
  ]);

  const projected = useMemo(
    () => conditions.map(_projectCondition).filter((c) => c !== null),
    [conditions],
  ) as CustomFormatConditionInput[];

  const score = Number.parseInt(scoreText, 10);
  const canSubmit =
    name.trim().length > 0 &&
    !Number.isNaN(score) &&
    score >= -10000 &&
    score <= 10000 &&
    projected.length > 0 &&
    !create.isPending;

  function _patch(index: number, patch: Partial<DraftCondition>): void {
    setConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    );
  }

  function _add(): void {
    setConditions((prev) => [...prev, _emptyCondition()]);
  }

  function _remove(index: number): void {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }

  function _onSubmit(e: React.FormEvent): void {
    e.preventDefault();
    if (!canSubmit) {
      return;
    }
    create.mutate(
      { name: name.trim(), score, conditions: projected },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("customFormats.create.success", { name: name.trim() }),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: err.message,
          });
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-cf-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <form
        onSubmit={_onSubmit}
        className="w-full max-w-2xl space-y-4 rounded-md border border-zinc-800 bg-zinc-950 p-4"
      >
        <h2 id="create-cf-title" className="text-base font-semibold text-zinc-100">
          {t("customFormats.create.title")}
        </h2>

        <label className="block space-y-1">
          <span className="text-xs font-medium text-zinc-400">
            {t("customFormats.create.name")}
          </span>
          <input
            type="text"
            required
            maxLength={128}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-xs font-medium text-zinc-400">
            {t("customFormats.create.score")}
          </span>
          <input
            type="number"
            min={-10000}
            max={10000}
            value={scoreText}
            onChange={(e) => setScoreText(e.target.value)}
            className="w-32 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100"
          />
        </label>

        <div className="space-y-2">
          <p className="text-xs font-medium text-zinc-400">
            {t("customFormats.create.conditions")}
          </p>
          <ul className="space-y-2">
            {conditions.map((c, i) => {
              const operatorOptions = _operatorsFor(c.field);
              const operator = operatorOptions.includes(c.operator)
                ? c.operator
                : operatorOptions[0];
              const inputType =
                c.field === "release_size" ? "number" : "text";
              return (
                <li
                  key={i}
                  className="flex flex-wrap items-center gap-2 rounded border border-zinc-800 bg-zinc-900/40 p-2"
                >
                  <select
                    aria-label={t("customFormats.create.field")}
                    value={c.field}
                    onChange={(e) =>
                      _patch(i, {
                        field: e.target.value as CustomFormatField,
                      })
                    }
                    className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
                  >
                    {_FIELDS.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label={t("customFormats.create.operator")}
                    value={operator}
                    onChange={(e) =>
                      _patch(i, {
                        operator: e.target.value as CustomFormatOperator,
                      })
                    }
                    className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
                  >
                    {operatorOptions.map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </select>
                  <input
                    type={inputType}
                    aria-label={t("customFormats.create.value")}
                    value={c.raw}
                    onChange={(e) => _patch(i, { raw: e.target.value })}
                    className="flex-1 min-w-32 rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-100"
                  />
                  {conditions.length > 1 && (
                    <button
                      type="button"
                      onClick={() => _remove(i)}
                      aria-label={t("customFormats.create.removeCondition")}
                      className="rounded border border-red-900/50 px-2 py-0.5 text-[0.65rem] text-red-400 hover:bg-red-950/40"
                    >
                      ×
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            onClick={_add}
            className="rounded-md border border-zinc-700 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            {t("customFormats.create.addCondition")}
          </button>
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            {t("customFormats.create.cancel")}
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending
              ? t("customFormats.create.saving")
              : t("customFormats.create.save")}
          </button>
        </div>
      </form>
    </div>
  );
}
