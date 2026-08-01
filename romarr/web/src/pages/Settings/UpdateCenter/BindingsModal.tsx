/**
 * Bindings management modal — per-(source, platform) overrides.
 *
 * Today only ``mode='skip'`` is honoured by the ingester. This
 * modal surfaces every platform slug the operator can toggle
 * (union of already-registered platforms + those already skipped
 * for this source), each with a checkbox that flips the skip
 * binding. Save replaces the full binding set for this source.
 *
 * ``prefer`` / ``merge`` modes are reserved for a follow-up
 * slice and not exposed in the UI yet.
 */

import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { usePlatforms } from "@/lib/api/queries/platforms";
import {
  useCommunitySourceBindings,
  useReplaceCommunitySourceBindings,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

interface Props {
  source: CommunitySource;
  onClose: () => void;
}

export function BindingsModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const { source } = props;
  const bindings = useCommunitySourceBindings(source.id);
  const platforms = usePlatforms();
  const replace = useReplaceCommunitySourceBindings();
  const pushToast = useToastStore((s) => s.push);

  // Local editable state: slug → skip? (starts from server data)
  const [skipSet, setSkipSet] = useState<Set<string>>(() => new Set());
  const [initialised, setInitialised] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!bindings.isSuccess || initialised) return;
    setSkipSet(
      new Set(
        bindings.data
          .filter((b) => b.mode === "skip")
          .map((b) => b.platform_slug),
      ),
    );
    setInitialised(true);
  }, [bindings.isSuccess, bindings.data, initialised]);

  // Universe of slugs to display : union of currently-registered
  // platforms + already-skipped slugs (some may not exist anymore).
  const slugs = useMemo(() => {
    const set = new Set<string>();
    (platforms.data ?? []).forEach((p) => set.add(p.slug));
    skipSet.forEach((s) => set.add(s));
    return [...set].sort();
  }, [platforms.data, skipSet]);

  const filteredSlugs = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return slugs;
    return slugs.filter((s) => s.toLowerCase().includes(needle));
  }, [slugs, filter]);

  const skippedCount = skipSet.size;

  function toggle(slug: string): void {
    setSkipSet((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  function submit(): void {
    replace.mutate(
      {
        sourceId: source.id,
        bindings: [...skipSet].map((slug) => ({
          source_id: source.id,
          platform_slug: slug,
          mode: "skip" as const,
        })),
      },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("updateCenter.bindingsSuccessTitle"),
            description: t("updateCenter.bindingsSuccessBody", {
              count: skippedCount,
            }),
          });
          props.onClose();
        },
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("updateCenter.bindingsErrorTitle"),
            description: err.message,
          }),
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("updateCenter.bindingsModalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-950/70 px-4 py-[4vh] backdrop-blur-sm sm:items-center"
      onClick={props.onClose}
    >
      <div
        className="flex w-full max-w-lg max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.bindingsModalTitle")}
          </h2>
          <p className="mt-0.5 truncate text-[0.65rem] text-zinc-500">
            {source.name}
          </p>
          <p className="mt-1 text-[0.7rem] text-zinc-400">
            {t("updateCenter.bindingsModalHint")}
          </p>
        </header>

        <div className="border-b border-zinc-800 px-4 py-2">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("updateCenter.bindingsFilterPlaceholder")}
            className="w-full rounded-md bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {(bindings.isPending || platforms.isPending) && (
            <p className="p-2 text-xs text-zinc-500">
              {t("updateCenter.loading")}
            </p>
          )}
          {bindings.isError && (
            <p role="alert" className="p-2 text-xs text-red-400">
              {bindings.error.message}
            </p>
          )}
          {filteredSlugs.length === 0 && bindings.isSuccess && (
            <p className="p-2 text-xs text-zinc-500">
              {t("updateCenter.bindingsNoSlugs")}
            </p>
          )}
          <ul className="grid grid-cols-1 gap-0.5 sm:grid-cols-2">
            {filteredSlugs.map((slug) => {
              const skipped = skipSet.has(slug);
              return (
                <li key={slug}>
                  <label
                    className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-zinc-800/60 ${
                      skipped ? "text-red-300" : "text-zinc-200"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={skipped}
                      onChange={() => toggle(slug)}
                      className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-950 accent-red-500"
                    />
                    <span className="truncate font-mono">{slug}</span>
                    {skipped && (
                      <span className="ml-auto shrink-0 rounded bg-red-950/40 px-1 text-[0.6rem] uppercase text-red-400">
                        {t("updateCenter.bindingsSkipTag")}
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-zinc-800 px-4 py-3">
          <p className="text-[0.65rem] text-zinc-500">
            {t("updateCenter.bindingsSkippedCount", { count: skippedCount })}
          </p>
          <div className="flex items-center gap-2">
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
              disabled={!initialised || replace.isPending}
              className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {replace.isPending
                ? t("updateCenter.bindingsSubmitting")
                : t("updateCenter.bindingsSubmit")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
