/**
 * CreateRegionProfileModal (slice 287).
 *
 * Single-step Add-new flow for the spec 006 Region Profile.
 * Operator types a name + comma-separated priorities (most-
 * preferred first) + optional comma-separated exclude list +
 * the fallback toggle.
 *
 * Cross-field validation:
 *   * priorities cannot be empty when fallback is disabled
 *     (the profile would reject every release);
 *   * priorities and exclude_regions cannot overlap.
 *
 * Strings resolve through ``settings:profiles.region.create.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { RegionMultiSelect } from "@/components/profiles/RegionMultiSelect";
import {
  useCreateRegionProfile,
  type RegionProfileCreate,
} from "@/lib/api/queries/region-profiles";
import { useToastStore } from "@/lib/store/toast";

interface CreateRegionProfileModalProps {
  onClose: () => void;
}

export function CreateRegionProfileModal(
  props: CreateRegionProfileModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateRegionProfile();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [priorities, setPriorities] = useState<string[]>(["EU", "WW", "US", "JP"]);
  const [excludeRegions, setExcludeRegions] = useState<string[]>([]);
  const [allowFallback, setAllowFallback] = useState(true);

  const submitting = create.isPending;

  const validationError: string | null = (() => {
    if (name.trim().length === 0)
      return t("profiles.region.create.errors.name");
    if (priorities.length === 0 && !allowFallback)
      return t("profiles.region.create.errors.emptyNoFallback");
    const overlap = priorities.filter((p) => excludeRegions.includes(p));
    if (overlap.length > 0)
      return t("profiles.region.create.errors.overlap", {
        regions: overlap.join(", "),
      });
    return null;
  })();
  const canSubmit = validationError === null;

  function commit(): void {
    if (!canSubmit) return;
    const payload: RegionProfileCreate = {
      name: name.trim(),
      priorities,
      exclude_regions: excludeRegions,
      allow_fallback_outside_priorities: allowFallback,
    };
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("profiles.region.create.successTitle"),
          description: t("profiles.region.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("profiles.region.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("profiles.region.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("profiles.region.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("profiles.region.create.subhead")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.region.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("profiles.region.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <div>
            <p className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.region.create.prioritiesLabel")}
            </p>
            <RegionMultiSelect
              mode="ordered"
              selected={priorities}
              onChange={setPriorities}
              disabled={submitting}
              conflictWith={excludeRegions}
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("profiles.region.create.prioritiesHint")}
            </p>
          </div>

          <div>
            <p className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.region.create.excludeLabel")}
            </p>
            <RegionMultiSelect
              mode="set"
              selected={excludeRegions}
              onChange={setExcludeRegions}
              disabled={submitting}
              conflictWith={priorities}
            />
          </div>

          <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
            <span className="text-xs text-zinc-300">
              {t("profiles.region.create.allowFallback")}
            </span>
            <input
              type="checkbox"
              checked={allowFallback}
              onChange={(e) => setAllowFallback(e.target.checked)}
              disabled={submitting}
              className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
            />
          </label>

          {validationError !== null && name.length > 0 && (
            <p
              role="status"
              className="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-1.5 text-[0.65rem] text-amber-200"
            >
              {validationError}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("profiles.region.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("profiles.region.create.submitting")
              : t("profiles.region.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
