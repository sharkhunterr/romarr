/**
 * Bindings management modal — per-(source, platform) overrides.
 *
 * Three modes exposed :
 *
 *   * ``use`` (default, no binding) — this source contributes to
 *     the slug normally. Its arrays merge with other sources'; its
 *     scalars win only if it's ranked highest in ``source_order``.
 *   * ``prefer`` — this source wins scalar fields for the slug
 *     even if another source is higher-ranked. Multiple ``prefer``
 *     bindings across sources for the same slug break on rank.
 *   * ``skip`` — this source's contribution for the slug is
 *     dropped entirely. Not counted in the array union.
 */

import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { usePlatforms } from "@/lib/api/queries/platforms";
import {
  useCommunitySourceBindings,
  useReplaceCommunitySourceBindings,
  type BindingMode,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

interface Props {
  source: CommunitySource;
  onClose: () => void;
}

type SlugMode = Extract<BindingMode, "skip" | "prefer">;

export function BindingsModal(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const { source } = props;
  const bindings = useCommunitySourceBindings(source.id);
  const platforms = usePlatforms();
  const replace = useReplaceCommunitySourceBindings();
  const pushToast = useToastStore((s) => s.push);

  // slug -> mode (absence = default 'use')
  const [modeBySlug, setModeBySlug] = useState<Record<string, SlugMode>>({});
  const [initialised, setInitialised] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!bindings.isSuccess || initialised) return;
    const next: Record<string, SlugMode> = {};
    bindings.data.forEach((b) => {
      if (b.mode === "skip" || b.mode === "prefer") {
        next[b.platform_slug] = b.mode;
      }
    });
    setModeBySlug(next);
    setInitialised(true);
  }, [bindings.isSuccess, bindings.data, initialised]);

  // Universe : known platforms + slugs already having a binding.
  const slugs = useMemo(() => {
    const set = new Set<string>();
    (platforms.data ?? []).forEach((p) => set.add(p.slug));
    Object.keys(modeBySlug).forEach((s) => set.add(s));
    return [...set].sort();
  }, [platforms.data, modeBySlug]);

  const filteredSlugs = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return slugs;
    return slugs.filter((s) => s.toLowerCase().includes(needle));
  }, [slugs, filter]);

  const skippedCount = Object.values(modeBySlug).filter((m) => m === "skip").length;
  const preferredCount = Object.values(modeBySlug).filter((m) => m === "prefer").length;

  function setMode(slug: string, mode: SlugMode | "use"): void {
    setModeBySlug((prev) => {
      const next = { ...prev };
      if (mode === "use") delete next[slug];
      else next[slug] = mode;
      return next;
    });
  }

  function submit(): void {
    const nextBindings = Object.entries(modeBySlug).map(([slug, mode]) => ({
      source_id: source.id,
      platform_slug: slug,
      mode,
    }));
    replace.mutate(
      { sourceId: source.id, bindings: nextBindings },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("updateCenter.bindingsSuccessTitle"),
            description: t("updateCenter.bindingsSuccessBody", {
              skip: skippedCount,
              prefer: preferredCount,
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
        className="flex w-full max-w-xl max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
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
          <ul className="space-y-1">
            {filteredSlugs.map((slug) => {
              const mode = modeBySlug[slug] ?? "use";
              return (
                <li
                  key={slug}
                  className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-zinc-800/40"
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-200">
                    {slug}
                  </span>
                  <div
                    role="radiogroup"
                    aria-label={slug}
                    className="inline-flex overflow-hidden rounded-md border border-zinc-700"
                  >
                    <ModeButton
                      label={t("updateCenter.bindingsModeUse")}
                      active={mode === "use"}
                      onClick={() => setMode(slug, "use")}
                      variant="neutral"
                    />
                    <ModeButton
                      label={t("updateCenter.bindingsModePrefer")}
                      active={mode === "prefer"}
                      onClick={() => setMode(slug, "prefer")}
                      variant="brand"
                    />
                    <ModeButton
                      label={t("updateCenter.bindingsModeSkip")}
                      active={mode === "skip"}
                      onClick={() => setMode(slug, "skip")}
                      variant="danger"
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-zinc-800 px-4 py-3">
          <p className="text-[0.65rem] text-zinc-500">
            {t("updateCenter.bindingsCounts", {
              prefer: preferredCount,
              skip: skippedCount,
            })}
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

interface ModeButtonProps {
  label: string;
  active: boolean;
  onClick: () => void;
  variant: "neutral" | "brand" | "danger";
}

function ModeButton(props: ModeButtonProps): ReactElement {
  const { label, active, onClick, variant } = props;
  let cls = "text-zinc-400 hover:bg-zinc-800/60";
  if (active) {
    if (variant === "brand") cls = "bg-brand/20 text-brand";
    else if (variant === "danger") cls = "bg-red-950/40 text-red-300";
    else cls = "bg-zinc-800 text-zinc-100";
  }
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`px-2.5 py-1 text-[0.65rem] font-medium transition-colors ${cls}`}
    >
      {label}
    </button>
  );
}
