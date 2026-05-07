/**
 * Two-column region picker (slice 350).
 *
 * Replaces the free-text comma-separated list operators had to
 * type before. Each region in the catalogue is shown with its
 * canonical label + the alias hint ("Europe — EU, EUR, Europe,
 * European") so the operator knows what filename inputs map into
 * each bucket. The component supports two modes:
 *
 *   * ``mode="ordered"`` — the selected list is a priority queue
 *     (Region Profile ``priorities``). Up/down buttons reorder.
 *   * ``mode="set"`` — the selected list is order-agnostic
 *     (Region Profile ``exclude_regions``). No reorder buttons.
 *
 * Codes outside the catalogue (legacy stored values, custom
 * codes) are preserved at the end of the selected list so we
 * never silently drop an existing profile setting.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  REGION_BY_CODE,
  REGION_CATALOGUE,
  type RegionCatalogueEntry,
} from "@/lib/regions/catalogue";

interface BaseProps {
  selected: readonly string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  /** Codes to grey out as already used by the *other* list
   * (priorities ↔ exclude_regions overlap is forbidden by the
   * backend). The component still lets the operator click them
   * — the parent surfaces the validation error. */
  conflictWith?: readonly string[];
}

interface OrderedProps extends BaseProps {
  mode: "ordered";
}
interface SetProps extends BaseProps {
  mode: "set";
}
type Props = OrderedProps | SetProps;

function _aliasHint(entry: RegionCatalogueEntry): string {
  return entry.aliases.join(", ");
}

export function RegionMultiSelect(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const { selected, onChange, disabled, conflictWith } = props;
  const conflicts = new Set(conflictWith ?? []);
  const selectedSet = new Set(selected);

  // Selected order: catalogue codes in selection order, then any
  // legacy / custom codes the catalogue doesn't list (preserve so
  // editing an old profile doesn't drop fields).
  const known = REGION_CATALOGUE.map((r) => r.code);
  const unknown = selected.filter((c) => !known.includes(c));
  const available = REGION_CATALOGUE.filter((r) => !selectedSet.has(r.code));

  function toggle(code: string): void {
    if (disabled) return;
    if (selectedSet.has(code)) {
      onChange(selected.filter((c) => c !== code));
    } else {
      onChange([...selected, code]);
    }
  }

  function move(code: string, dir: -1 | 1): void {
    if (disabled) return;
    const idx = selected.indexOf(code);
    if (idx === -1) return;
    const swap = idx + dir;
    if (swap < 0 || swap >= selected.length) return;
    const next = [...selected];
    [next[idx], next[swap]] = [next[swap]!, next[idx]!];
    onChange(next);
  }

  return (
    <div className="space-y-2">
      <div>
        <p className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
          {t(
            props.mode === "ordered"
              ? "profiles.region.picker.selectedOrdered"
              : "profiles.region.picker.selectedSet",
          )}
        </p>
        {selected.length === 0 ? (
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-950/40 px-3 py-2 text-[0.7rem] italic text-zinc-500">
            {t("profiles.region.picker.emptySelected")}
          </p>
        ) : (
          <ul className="space-y-1">
            {selected.map((code, i) => {
              const entry = REGION_BY_CODE[code];
              const labelKey = entry?.i18nKey;
              const label = labelKey
                ? t(`profiles.region.catalogue.${labelKey}`)
                : code;
              const hint = entry ? _aliasHint(entry) : code;
              return (
                <li
                  key={code}
                  className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/40 px-2 py-1.5"
                >
                  {props.mode === "ordered" && (
                    <span className="w-5 shrink-0 text-right font-mono text-[0.65rem] text-zinc-500">
                      {i + 1}.
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-zinc-100">
                      {label}
                    </p>
                    <p className="truncate text-[0.6rem] text-zinc-500">
                      {hint}
                    </p>
                  </div>
                  {props.mode === "ordered" && (
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => move(code, -1)}
                        disabled={disabled || i === 0}
                        title={t("profiles.region.picker.moveUp")}
                        className="grid h-7 w-7 place-items-center rounded border border-zinc-700 text-xs text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => move(code, 1)}
                        disabled={disabled || i === selected.length - 1}
                        title={t("profiles.region.picker.moveDown")}
                        className="grid h-7 w-7 place-items-center rounded border border-zinc-700 text-xs text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        ↓
                      </button>
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => toggle(code)}
                    disabled={disabled}
                    title={t("profiles.region.picker.remove")}
                    className="grid h-7 w-7 shrink-0 place-items-center rounded border border-red-900/50 text-xs text-red-400 hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    ×
                  </button>
                </li>
              );
            })}
            {unknown.length > 0 && (
              <li className="rounded-md border border-dashed border-amber-900/40 bg-amber-950/10 px-2 py-1 text-[0.6rem] text-amber-300">
                {t("profiles.region.picker.legacy", {
                  codes: unknown.join(", "),
                })}
              </li>
            )}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
          {t("profiles.region.picker.available")}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {available.length === 0 ? (
            <p className="text-[0.7rem] italic text-zinc-500">
              {t("profiles.region.picker.allSelected")}
            </p>
          ) : (
            available.map((entry) => {
              const conflict = conflicts.has(entry.code);
              return (
                <button
                  key={entry.code}
                  type="button"
                  onClick={() => toggle(entry.code)}
                  disabled={disabled}
                  title={_aliasHint(entry)}
                  className={[
                    "rounded-md border px-2 py-1 text-[0.7rem]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                    "disabled:cursor-not-allowed disabled:opacity-40",
                    conflict
                      ? "border-amber-900/50 bg-amber-950/20 text-amber-300 hover:bg-amber-950/40"
                      : "border-zinc-700 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-800",
                  ].join(" ")}
                >
                  {t(`profiles.region.catalogue.${entry.i18nKey}`)}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
