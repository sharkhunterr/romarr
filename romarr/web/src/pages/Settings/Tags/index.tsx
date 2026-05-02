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

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTags } from "@/lib/api/queries/tags";

import { CreateTagForm } from "./CreateTagForm";
import { TagRow } from "./TagRow";

export function TagsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const { data, isPending, isError, error } = useTags();

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
        <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          {t("tags.existing")}
        </h3>

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
        ) : (
          <ul className="space-y-2">
            {data.map((tag) => (
              <TagRow key={tag.id} tag={tag} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
