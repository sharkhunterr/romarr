/**
 * Edit-game modal (post-add).
 *
 * Backs the "Modifier" button on the game detail header — lets
 * the operator change ``monitored`` and the library binding
 * AFTER the game was already added. Mirrors AddGameModal's field
 * set (minus platform, which is intentionally not editable on an
 * existing game — its ``uq_game_platform_slug`` invariant would
 * make a swap indistinguishable from a create).
 *
 * Real-world driver: an operator adds "The Legend of Zelda"
 * (NES) already having a copy on disk. Without this modal they
 * can't disable auto-grab post-add and cutoff keeps re-grabbing
 * on every schedule tick.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { Game } from "@/lib/api/queries/games";
import { useUpdateGame } from "@/lib/api/queries/games";
import { useLibraries } from "@/lib/api/queries/libraries";
import { useQualityProfiles } from "@/lib/api/queries/quality-profiles";
import { useToastStore } from "@/lib/store/toast";

interface EditGameModalProps {
  game: Game;
  onClose: () => void;
}

export function EditGameModal(props: EditGameModalProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const libraries = useLibraries();
  const qualityProfiles = useQualityProfiles();
  const update = useUpdateGame();

  const [libraryId, setLibraryId] = useState<number | null>(
    props.game.library_id ?? null,
  );
  const [monitored, setMonitored] = useState<boolean>(props.game.monitored);

  const selectedLibrary = (libraries.data ?? []).find(
    (lib) => lib.id === libraryId,
  );
  const selectedQualityProfile = (qualityProfiles.data ?? []).find(
    (q) => q.id === selectedLibrary?.quality_profile_id,
  );

  const dirty =
    monitored !== props.game.monitored ||
    (libraryId ?? null) !== (props.game.library_id ?? null);

  function submit(): void {
    if (!dirty) {
      props.onClose();
      return;
    }
    update.mutate(
      {
        gameId: props.game.id,
        monitored:
          monitored !== props.game.monitored ? monitored : undefined,
        libraryId:
          (libraryId ?? null) !== (props.game.library_id ?? null)
            ? libraryId
            : undefined,
      },
      {
        onSuccess: (game) => {
          pushToast({
            kind: "success",
            title: t("edit.successTitle"),
            description: t("edit.successBody", { title: game.title }),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("edit.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("edit.modalTitle", { title: props.game.title })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("edit.modalTitle", { title: props.game.title })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("edit.subtitle")}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-4 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("edit.libraryLabel")}
            </span>
            {libraries.isPending ? (
              <p className="text-xs text-zinc-500">
                {t("edit.loadingLibraries")}
              </p>
            ) : libraries.isError ? (
              <p className="text-xs text-red-400">{libraries.error.message}</p>
            ) : (libraries.data ?? []).length === 0 ? (
              <p className="text-xs text-amber-400">{t("edit.noLibraries")}</p>
            ) : (
              <select
                value={libraryId ?? ""}
                onChange={(e) =>
                  setLibraryId(e.target.value ? Number(e.target.value) : null)
                }
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <option value="">{t("edit.libraryUnbound")}</option>
                {libraries.data!.map((lib) => (
                  <option key={lib.id} value={lib.id}>
                    {lib.name} — {lib.path}
                  </option>
                ))}
              </select>
            )}
          </label>

          <div className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("edit.profileLabel")}
            </span>
            <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-sm">
              {selectedQualityProfile ? (
                <>
                  <span className="text-zinc-100">
                    {selectedQualityProfile.name}
                  </span>
                  <span className="ml-2 text-[0.7rem] text-zinc-500">
                    {t("edit.profileMinScore", {
                      score: selectedQualityProfile.auto_grab_min_score,
                    })}
                  </span>
                </>
              ) : (
                <span className="text-xs text-zinc-500">
                  {t("edit.profileFromLibrary")}
                </span>
              )}
            </div>
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={monitored}
              onChange={(e) => setMonitored(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-brand"
            />
            <span className="text-sm text-zinc-200">
              {t("edit.monitoredLabel")}
            </span>
          </label>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 p-3 text-[0.65rem] text-zinc-500">
            {t("edit.monitoredHint")}
          </p>

          {update.isError && (
            <p role="alert" className="text-xs text-red-400">
              {update.error.message}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("edit.cancel")}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!dirty || update.isPending}
            className={[
              "rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900",
              "hover:bg-brand-300",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {update.isPending ? t("edit.submitting") : t("edit.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
