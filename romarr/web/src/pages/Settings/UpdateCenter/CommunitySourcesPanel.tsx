/**
 * Reusable community-sources block, scoped to one ``resource_type``.
 *
 * Same data / same visual as the Update Center page, but filtered
 * so a Custom Formats settings tab shows only CF sources and a
 * Platforms page shows only platform-pack sources. All operations
 * (add, apply, delete, toggle...) still hit the unified
 * ``/api/v3/community/*`` API — so a source added here also shows
 * up in Paramètres > Mises à jour and vice-versa.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  useCommunitySources,
  type CommunityResourceType,
} from "@/lib/api/queries/community";

import { AddCommunitySourceModal } from "./AddCommunitySourceModal";
import { CommunitySourceRow } from "./CommunitySourceRow";

interface Props {
  resourceType: CommunityResourceType;
  /** Section heading. Defaults to i18n ``updateCenter.panelTitle``. */
  title?: string;
  /** Subtitle under the heading. */
  subtitle?: string;
}

export function CommunitySourcesPanel(props: Props): ReactElement {
  const { t } = useTranslation("settings");
  const sources = useCommunitySources(props.resourceType);
  const [addOpen, setAddOpen] = useState(false);

  const count = sources.data?.length ?? 0;

  return (
    <section className="space-y-3 rounded-md border border-zinc-800 bg-zinc-950/30 p-3">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">
            {props.title ?? t("updateCenter.panelTitle")}
            {count > 0 && (
              <span className="ml-2 rounded bg-zinc-800 px-1.5 py-px text-[0.65rem] font-normal text-zinc-400">
                {count}
              </span>
            )}
          </h3>
          <p className="mt-0.5 text-[0.7rem] text-zinc-500">
            {props.subtitle ?? t("updateCenter.panelSubtitle")}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            to="/settings/updates"
            className="text-[0.65rem] text-brand underline hover:text-brand-300"
            title={t("updateCenter.panelSeeAllHint")}
          >
            {t("updateCenter.panelSeeAll")}
          </Link>
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="rounded-md border border-zinc-700 px-2.5 py-1 text-[0.7rem] font-medium text-zinc-200 hover:bg-zinc-800"
          >
            + {t("updateCenter.addSource")}
          </button>
        </div>
      </header>

      {sources.isPending && (
        <p className="text-xs text-zinc-500">
          {t("updateCenter.loading")}
        </p>
      )}
      {sources.isError && (
        <p role="alert" className="text-xs text-red-400">
          {sources.error.message}
        </p>
      )}
      {sources.isSuccess && sources.data.length === 0 && (
        <p className="rounded border border-dashed border-zinc-800 bg-zinc-900/30 p-3 text-center text-[0.7rem] text-zinc-500">
          {t("updateCenter.panelEmpty")}
        </p>
      )}
      {sources.isSuccess && sources.data.length > 0 && (
        <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          {sources.data.map((src) => (
            <CommunitySourceRow key={src.id} source={src} />
          ))}
        </div>
      )}

      {addOpen && (
        <AddCommunitySourceModal
          prefilledResourceType={props.resourceType}
          onClose={() => setAddOpen(false)}
        />
      )}
    </section>
  );
}
