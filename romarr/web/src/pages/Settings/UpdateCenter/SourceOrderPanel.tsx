/**
 * Drag-and-drop rank editor for the global ``source_order``.
 *
 * The platform materializer breaks scalar ties (name, manufacturer,
 * …) using this order when no ``prefer`` binding wins. Higher rank
 * = closer to the top of the list.
 *
 * Only shown for the ``platform_pack`` resource type — the order
 * doesn't apply to CFs.
 */

import { GripVertical } from "lucide-react";
import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCommunitySources,
  useReplaceSourceOrder,
  useSourceOrder,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

export function SourceOrderPanel(): ReactElement | null {
  const { t } = useTranslation("settings");
  const platformSources = useCommunitySources("platform_pack");
  const order = useSourceOrder();
  const save = useReplaceSourceOrder();
  const pushToast = useToastStore((s) => s.push);

  const [ranked, setRanked] = useState<number[]>([]);
  const [dragging, setDragging] = useState<number | null>(null);

  const sourcesById: Map<number, CommunitySource> = useMemo(() => {
    const m = new Map<number, CommunitySource>();
    (platformSources.data ?? []).forEach((s) => m.set(s.id, s));
    return m;
  }, [platformSources.data]);

  // Compose the display list : saved order first, then any
  // platform source not yet ranked appended by id.
  useEffect(() => {
    if (!platformSources.isSuccess || !order.isSuccess) return;
    const knownIds = new Set(platformSources.data.map((s) => s.id));
    const filtered = order.data.source_order.filter((id) => knownIds.has(id));
    const missing = platformSources.data
      .map((s) => s.id)
      .filter((id) => !filtered.includes(id))
      .sort((a, b) => a - b);
    setRanked([...filtered, ...missing]);
  }, [platformSources.isSuccess, order.isSuccess, platformSources.data, order.data]);

  const dirty = useMemo(() => {
    if (!order.isSuccess) return false;
    const saved = order.data.source_order;
    if (saved.length !== ranked.length) return true;
    return saved.some((id, i) => ranked[i] !== id);
  }, [order.isSuccess, order.data, ranked]);

  function onDragStart(idx: number): void {
    setDragging(idx);
  }

  function onDragOver(e: React.DragEvent, idx: number): void {
    e.preventDefault();
    if (dragging === null || dragging === idx) return;
    setRanked((prev) => {
      if (dragging < 0 || dragging >= prev.length) return prev;
      const next = [...prev];
      const moved = next.splice(dragging, 1)[0]!;
      next.splice(idx, 0, moved);
      setDragging(idx);
      return next;
    });
  }

  function onDragEnd(): void {
    setDragging(null);
  }

  function commit(): void {
    save.mutate(ranked, {
      onSuccess: () =>
        pushToast({
          kind: "success",
          title: t("updateCenter.orderSuccessTitle"),
          description: t("updateCenter.orderSuccessBody"),
        }),
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("updateCenter.orderErrorTitle"),
          description: err.message,
        }),
    });
  }

  if (platformSources.isPending || order.isPending) {
    return null;
  }
  if (
    !platformSources.isSuccess ||
    !order.isSuccess ||
    platformSources.data.length < 2
  ) {
    // Ordering only makes sense with at least 2 platform sources.
    return null;
  }

  return (
    <section className="space-y-3 rounded-md border border-zinc-800 bg-zinc-950/30 p-3">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.orderPanelTitle")}
          </h3>
          <p className="mt-0.5 text-[0.7rem] text-zinc-500">
            {t("updateCenter.orderPanelSubtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={commit}
          disabled={!dirty || save.isPending}
          className="shrink-0 rounded-md bg-brand px-3 py-1 text-[0.7rem] font-medium text-zinc-900 hover:bg-brand-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending
            ? t("updateCenter.orderSaving")
            : t("updateCenter.orderSave")}
        </button>
      </header>

      <ol className="space-y-1">
        {ranked.map((id, idx) => {
          const src = sourcesById.get(id);
          if (!src) return null;
          const isDragging = dragging === idx;
          return (
            <li
              key={id}
              draggable
              onDragStart={() => onDragStart(idx)}
              onDragOver={(e) => onDragOver(e, idx)}
              onDragEnd={onDragEnd}
              className={`flex items-center gap-2 rounded border px-2 py-1.5 ${
                isDragging
                  ? "border-brand/40 bg-brand/5"
                  : "border-zinc-800 bg-zinc-900/40"
              } cursor-move`}
            >
              <span className="text-zinc-500">
                <GripVertical size={14} aria-hidden="true" />
              </span>
              <span className="w-6 shrink-0 text-right font-mono text-[0.65rem] text-zinc-500 tabular-nums">
                {idx + 1}.
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-zinc-100">
                {src.name}
              </span>
              <span className="hidden shrink-0 truncate font-mono text-[0.6rem] text-zinc-500 sm:inline">
                #{src.id}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
