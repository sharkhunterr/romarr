/**
 * Settings > Media Management (slice 92).
 *
 * Library audit list against /api/v3/rom/library. Read-only
 * inspection + delete (with the documented force-detach
 * fallback when bound Releases reject the plain DELETE);
 * create + edit forms deferred until the multi-step library
 * editor lands.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useLibraries } from "@/lib/api/queries/libraries";

import { CreateLibraryModal } from "./CreateLibraryModal";
import { LibraryRow } from "./LibraryRow";

export function MediaManagementPage(): ReactElement {
  const { t } = useTranslation("settings");
  const libraries = useLibraries();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-zinc-100">
            {t("mediaManagement.title")}
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {t("mediaManagement.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("mediaManagement.create.openButton")}
        </button>
      </header>

      {createOpen && (
        <CreateLibraryModal onClose={() => setCreateOpen(false)} />
      )}

      {libraries.isLoading && <ListSkeleton rows={3} />}
      {libraries.isError && (
        <EmptyState
          title={t("mediaManagement.empty.title")}
          description={libraries.error.message}
        />
      )}
      {libraries.isSuccess && libraries.data.length === 0 && (
        <EmptyState
          title={t("mediaManagement.empty.title")}
          description={t("mediaManagement.empty.body")}
        />
      )}
      {libraries.isSuccess && libraries.data.length > 0 && (
        <>
          <ul className="space-y-2">
            {libraries.data.map((library) => (
              <LibraryRow key={library.id} library={library} />
            ))}
          </ul>
          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("mediaManagement.editorHint")}
          </p>
        </>
      )}
    </div>
  );
}
