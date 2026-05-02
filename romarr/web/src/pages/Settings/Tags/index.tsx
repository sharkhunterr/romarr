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
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useTags } from "@/lib/api/queries/tags";

import { CreateTagForm } from "./CreateTagForm";
import { TagRow } from "./TagRow";

export function TagsPage(): ReactElement {
  const { data, isPending, isError, error } = useTags();

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          Tags
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Polymorphic tags applied across Games, Indexers,
          Notifications, and Releases. Renaming a tag updates
          every entity it touches.
        </p>
      </header>

      <CreateTagForm />

      <section className="mt-6">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          Existing tags
        </h2>

        {isPending ? (
          <ListSkeleton rows={4} />
        ) : isError ? (
          <EmptyState
            title="Couldn't load tags"
            description={error.message}
          />
        ) : data.length === 0 ? (
          <EmptyState
            title="No tags yet"
            description="Create one above to start tagging Games, Indexers, Notifications, or Releases."
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
