/**
 * CustomFormatEditorModal — Radarr-style visual editor for
 * Custom Formats. Handles both create and edit flows.
 *
 * UX highlights:
 *   * Field/operator/value builder for each condition (v1 flat
 *     list; OR grouping deferred).
 *   * Live preview: operator pastes a sample indexer title and
 *     the panel lights the conditions that match — validates
 *     regex patterns before saving.
 *   * `title` field pulls the raw indexer title (Radarr's
 *     "Release Title" equivalent) so operators can filter
 *     Music/OST/Manual/etc. entries the parser can't classify.
 *   * Regex is validated client-side; broken patterns disable
 *     the Save button with an inline error.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateCustomFormat,
  useUpdateCustomFormat,
  type CustomFormat,
  type CustomFormatConditionInput,
  type CustomFormatField,
  type CustomFormatOperator,
} from "@/lib/api/queries/custom-formats";
import { useToastStore } from "@/lib/store/toast";

interface CustomFormatEditorModalProps {
  onClose: () => void;
  /** Present when editing an existing format; absent when creating. */
  format?: CustomFormat;
}

const _FIELDS: ReadonlyArray<CustomFormatField> = [
  "title",
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
  "matches_regex",
  "equals",
  "contains",
  "in",
  "not_in",
];

const _NUMERIC_OPERATORS: ReadonlyArray<CustomFormatOperator> = [
  "greater_than",
  "less_than",
  "equals",
];

function _operatorsFor(
  field: CustomFormatField,
): readonly CustomFormatOperator[] {
  return field === "release_size" ? _NUMERIC_OPERATORS : _STRING_OPERATORS;
}

interface DraftCondition {
  field: CustomFormatField;
  operator: CustomFormatOperator;
  raw: string;
  regexError?: string;
}

function _emptyCondition(): DraftCondition {
  return { field: "title", operator: "matches_regex", raw: "" };
}

function _projectCondition(
  draft: DraftCondition,
): CustomFormatConditionInput | null {
  const value = draft.raw.trim();
  if (!value) return null;
  if (draft.operator === "in" || draft.operator === "not_in") {
    const parts = value
      .split(/[,;\n]/)
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
    if (parts.length === 0) return null;
    return { field: draft.field, operator: draft.operator, values: parts };
  }
  if (draft.field === "release_size") {
    const num = Number(value);
    if (Number.isNaN(num)) return null;
    return { field: draft.field, operator: draft.operator, values: num };
  }
  return { field: draft.field, operator: draft.operator, values: value };
}

function _validateRegex(pattern: string): string | undefined {
  try {
    // eslint-disable-next-line no-new
    new RegExp(pattern);
    return undefined;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}

function _draftsFromFormat(fmt: CustomFormat): DraftCondition[] {
  const drafts = fmt.conditions.map((raw): DraftCondition => {
    const field = (raw.field ?? "title") as CustomFormatField;
    const operator = (raw.operator ?? "matches_regex") as CustomFormatOperator;
    const values = raw.values;
    let rawValue: string;
    if (Array.isArray(values)) {
      rawValue = values.map((v) => String(v)).join(", ");
    } else if (values === null || values === undefined) {
      rawValue = "";
    } else {
      rawValue = String(values);
    }
    const draft: DraftCondition = { field, operator, raw: rawValue };
    if (operator === "matches_regex") {
      draft.regexError = _validateRegex(rawValue);
    }
    return draft;
  });
  return drafts.length > 0 ? drafts : [_emptyCondition()];
}

// Given a sample string, does this projected condition match it?
// Only meaningful for `title` — other fields need per-release facts
// the modal doesn't have, so we surface a "?" indicator instead.
function _previewMatches(
  cond: CustomFormatConditionInput,
  sample: string,
): "match" | "no-match" | "n/a" {
  if (cond.field !== "title") return "n/a";
  const value = String(cond.values);
  if (cond.operator === "matches_regex") {
    try {
      return new RegExp(value).test(sample) ? "match" : "no-match";
    } catch {
      return "n/a";
    }
  }
  if (cond.operator === "equals") {
    return sample === value ? "match" : "no-match";
  }
  if (cond.operator === "contains") {
    return sample.includes(value) ? "match" : "no-match";
  }
  if (cond.operator === "in" && Array.isArray(cond.values)) {
    return cond.values.map(String).includes(sample) ? "match" : "no-match";
  }
  if (cond.operator === "not_in" && Array.isArray(cond.values)) {
    return cond.values.map(String).includes(sample) ? "no-match" : "match";
  }
  return "n/a";
}

export function CustomFormatEditorModal(
  props: CustomFormatEditorModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateCustomFormat();
  const update = useUpdateCustomFormat();
  const pushToast = useToastStore((s) => s.push);
  const isEdit = props.format !== undefined;
  const busy = create.isPending || update.isPending;

  const [name, setName] = useState(props.format?.name ?? "");
  const [scoreText, setScoreText] = useState(
    props.format ? String(props.format.score) : "0",
  );
  const [conditions, setConditions] = useState<DraftCondition[]>(
    props.format ? _draftsFromFormat(props.format) : [_emptyCondition()],
  );
  const [sampleTitle, setSampleTitle] = useState(
    "[MiNERVA Archive] [No-Intro] [Nintendo - Nintendo Music (M4A)] [World] " +
      "Kirby's Dream Land [ZIP]",
  );

  const projected = useMemo(
    () =>
      conditions
        .map(_projectCondition)
        .filter((c): c is CustomFormatConditionInput => c !== null),
    [conditions],
  );

  const score = Number.parseInt(scoreText, 10);
  const hasRegexError = conditions.some((c) => c.regexError);
  const canSubmit =
    !busy &&
    name.trim().length > 0 &&
    !Number.isNaN(score) &&
    score >= -10000 &&
    score <= 10000 &&
    projected.length > 0 &&
    !hasRegexError;

  function _patch(index: number, patch: Partial<DraftCondition>): void {
    setConditions((prev) =>
      prev.map((c, i) => {
        if (i !== index) return c;
        const next: DraftCondition = { ...c, ...patch };
        if (next.operator === "matches_regex") {
          next.regexError = next.raw ? _validateRegex(next.raw) : undefined;
        } else {
          next.regexError = undefined;
        }
        return next;
      }),
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
    if (!canSubmit) return;
    const successMsg = isEdit
      ? t("customFormats.editor.updateSuccess", { name: name.trim() })
      : t("customFormats.editor.createSuccess", { name: name.trim() });
    const handleError = (err: { message: string }): void => {
      pushToast({ kind: "error", title: err.message });
    };
    if (isEdit && props.format) {
      update.mutate(
        {
          id: props.format.id,
          payload: {
            name: name.trim(),
            score,
            conditions: projected,
          },
        },
        {
          onSuccess: () => {
            pushToast({ kind: "success", title: successMsg });
            props.onClose();
          },
          onError: handleError,
        },
      );
    } else {
      create.mutate(
        { name: name.trim(), score, conditions: projected },
        {
          onSuccess: () => {
            pushToast({ kind: "success", title: successMsg });
            props.onClose();
          },
          onError: handleError,
        },
      );
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cf-editor-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <form
        onSubmit={_onSubmit}
        className="grid max-h-[90vh] w-full max-w-3xl gap-4 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950 p-5"
      >
        <div className="flex items-center justify-between gap-3">
          <h2
            id="cf-editor-title"
            className="text-base font-semibold text-zinc-100"
          >
            {isEdit
              ? t("customFormats.editor.editTitle", {
                  name: props.format?.name ?? "",
                })
              : t("customFormats.editor.createTitle")}
          </h2>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            aria-label={t("customFormats.editor.close")}
          >
            ✕
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto]">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-zinc-400">
              {t("customFormats.editor.name")}
            </span>
            <input
              type="text"
              required
              maxLength={128}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 focus:border-brand focus:outline-none"
              placeholder={t("customFormats.editor.namePlaceholder")}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-zinc-400">
              {t("customFormats.editor.score")}
            </span>
            <input
              type="number"
              min={-10000}
              max={10000}
              value={scoreText}
              onChange={(e) => setScoreText(e.target.value)}
              className="w-32 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 focus:border-brand focus:outline-none"
            />
          </label>
        </div>
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/30 p-2 text-[0.7rem] text-zinc-500">
          {t("customFormats.editor.scoreHint")}
        </p>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-zinc-300">
              {t("customFormats.editor.conditions")}
            </p>
            <button
              type="button"
              onClick={_add}
              className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
            >
              + {t("customFormats.editor.addCondition")}
            </button>
          </div>
          <p className="text-[0.7rem] text-zinc-500">
            {t("customFormats.editor.conditionsHint")}
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
                  className="space-y-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      aria-label={t("customFormats.editor.field")}
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
                          {t(`customFormats.editor.fieldName.${f}`)}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label={t("customFormats.editor.operator")}
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
                          {t(`customFormats.editor.operatorName.${op}`)}
                        </option>
                      ))}
                    </select>
                    <input
                      type={inputType}
                      aria-label={t("customFormats.editor.value")}
                      value={c.raw}
                      onChange={(e) => _patch(i, { raw: e.target.value })}
                      placeholder={
                        operator === "matches_regex"
                          ? "\\bMusic\\b|OST"
                          : operator === "in" || operator === "not_in"
                            ? "a, b, c"
                            : ""
                      }
                      className={[
                        "min-w-32 flex-1 rounded border bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-100",
                        c.regexError
                          ? "border-red-800"
                          : "border-zinc-800 focus:border-brand focus:outline-none",
                      ].join(" ")}
                    />
                    {conditions.length > 1 && (
                      <button
                        type="button"
                        onClick={() => _remove(i)}
                        aria-label={t(
                          "customFormats.editor.removeCondition",
                        )}
                        className="rounded border border-red-900/50 px-2 py-0.5 text-[0.65rem] text-red-400 hover:bg-red-950/40"
                      >
                        ×
                      </button>
                    )}
                  </div>
                  {c.regexError && (
                    <p className="pl-1 text-[0.7rem] text-red-400">
                      {t("customFormats.editor.regexError")}: {c.regexError}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-900/20 p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-zinc-300">
              {t("customFormats.editor.preview")}
            </p>
            <span className="text-[0.65rem] text-zinc-500">
              {t("customFormats.editor.previewSubtitle")}
            </span>
          </div>
          <input
            type="text"
            value={sampleTitle}
            onChange={(e) => setSampleTitle(e.target.value)}
            className="w-full rounded border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-100"
            placeholder={t("customFormats.editor.previewPlaceholder")}
          />
          <ul className="space-y-1">
            {projected.length === 0 && (
              <li className="text-[0.7rem] text-zinc-500">
                {t("customFormats.editor.previewEmpty")}
              </li>
            )}
            {projected.map((cond, i) => {
              const status = _previewMatches(cond, sampleTitle);
              const tone =
                status === "match"
                  ? "bg-brand/20 text-brand"
                  : status === "no-match"
                    ? "bg-red-950/40 text-red-400"
                    : "bg-zinc-800 text-zinc-500";
              const label =
                status === "match"
                  ? "✓"
                  : status === "no-match"
                    ? "✗"
                    : "?";
              return (
                <li
                  key={i}
                  className="flex items-center gap-2 text-[0.7rem] text-zinc-400"
                >
                  <span
                    className={`inline-block w-6 rounded px-1 text-center font-mono ${tone}`}
                  >
                    {label}
                  </span>
                  <span className="font-mono text-zinc-500">
                    {cond.field} · {cond.operator} ·{" "}
                    <span className="text-zinc-300">
                      {Array.isArray(cond.values)
                        ? cond.values.join(", ")
                        : String(cond.values)}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="text-[0.65rem] text-zinc-500">
            {t("customFormats.editor.previewNote")}
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-zinc-900 pt-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            {t("customFormats.editor.cancel")}
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy
              ? t("customFormats.editor.saving")
              : isEdit
                ? t("customFormats.editor.update")
                : t("customFormats.editor.save")}
          </button>
        </div>
      </form>
    </div>
  );
}
