/**
 * Settings > Tags page (P-SET sub-page).
 *
 * Full CRUD against the spec 013 /api/v3/tag* surface (slice
 * 24): list every tag, create new ones, inline-edit
 * label / color, delete with the documented force-cascade
 * fallback when the tag is in use.
 *
 * Polymorphic /detail/{id} drill-in is deferred until a
 * dedicated tag-detail surface lands; today the row carries
 * just the tag itself.
 *
 * Strings resolve through `settings:tags.*` (slice 66).
 * Lives under SettingsLayout (slice 53) so the outer
 * page chrome (header / sidebar) is owned upstream — this
 * component renders only the tab content.
 */

import { useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTags } from "@/lib/api/queries/tags";

import { CreateTagForm } from "./CreateTagForm";
import { TagRow } from "./TagRow";

export function TagsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const [searchParams, setSearchParams] = useSearchParams();
  const unusedOnly = searchParams.get("unusedOnly") === "true";
  const { data, isPending, isError, error } = useTags();

  const setUnusedOnly = (next: boolean): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next) params.set("unusedOnly", "true");
        else params.delete("unusedOnly");
        return params;
      },
      { replace: false },
    );
  };

  const filtered = useMemo(() => {
    if (!data) return [];
    return unusedOnly
      ? data.filter((tag) => tag.usageCount === 0)
      : data;
  }, [data, unusedOnly]);

  const totalCount = data?.length ?? 0;
  const unusedCount = useMemo(
    () => (data ?? []).filter((t) => t.usageCount === 0).length,
    [data],
  );

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("tags.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{t("tags.subtitle")}</p>
      </header>

      <CreateTagForm />

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-mono text-xs uppercase tracking-widest text-zinc-500">
            {t("tags.existing")}
          </h3>
          {totalCount > 0 && (
            <button
              type="button"
              onClick={() => setUnusedOnly(!unusedOnly)}
              aria-pressed={unusedOnly}
              disabled={unusedCount === 0 && !unusedOnly}
              className={[
                "rounded-md px-3 py-1 text-xs font-medium ring-1 ring-inset",
                "transition-colors",
                unusedOnly
                  ? "bg-amber-700/30 text-amber-200 ring-amber-500/40"
                  : "bg-zinc-900/40 text-zinc-400 ring-zinc-700 hover:bg-zinc-800",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-50",
              ].join(" ")}
            >
              {unusedOnly
                ? t("tags.filter.unusedOnly.on", { count: unusedCount })
                : t("tags.filter.unusedOnly.off", { count: unusedCount })}
            </button>
          )}
        </div>

        {isPending ? (
          <ListSkeleton rows={4} />
        ) : isError ? (
          <EmptyState
            title={t("tags.loadError")}
            description={error.message}
          />
        ) : data.length === 0 ? (
          <EmptyState
            title={t("tags.empty.title")}
            description={t("tags.empty.body")}
          />
        ) : filtered.length === 0 ? (
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("tags.filter.noMatches")}
          </p>
        ) : (
          <ul className="space-y-2">
            {filtered.map((tag) => (
              <TagRow key={tag.id} tag={tag} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
