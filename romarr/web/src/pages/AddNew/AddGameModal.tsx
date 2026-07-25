/**
 * Add-to-Library modal for the AddNew page (slice 145).
 *
 * Operator picks a Platform and a monitored toggle, then we
 * fire `POST /api/v3/game/lookup/add` and navigate to the new
 * Game's detail page on success.
 *
 * Strings resolve through the ``addNew`` namespace.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useLibraries } from "@/lib/api/queries/libraries";
import {
  useAddGameFromLookup,
  type GameLookupRow,
} from "@/lib/api/queries/lookup";
import { usePlatforms } from "@/lib/api/queries/platforms";
import { useQualityProfiles } from "@/lib/api/queries/quality-profiles";
import { useToastStore } from "@/lib/store/toast";

interface AddGameModalProps {
  candidate: GameLookupRow;
  onClose: () => void;
}

export function AddGameModal(props: AddGameModalProps): ReactElement {
  const { t } = useTranslation("addNew");
  const navigate = useNavigate();
  const pushToast = useToastStore((s) => s.push);
  const platforms = usePlatforms();
  const libraries = useLibraries();
  const qualityProfiles = useQualityProfiles();
  const add = useAddGameFromLookup();

  const [platformId, setPlatformId] = useState<number | null>(null);
  const [libraryId, setLibraryId] = useState<number | null>(null);
  const [monitored, setMonitored] = useState(true);

  // The quality / region / dump / language / naming profiles are
  // a property of the LIBRARY, not the game — picking a library
  // IS picking the profile cascade. Resolve the selected
  // library's quality profile so the operator sees which one
  // will gate this game's auto-grabs (incl. the min-score floor)
  // without leaving the modal.
  const selectedLibrary = (libraries.data ?? []).find(
    (lib) => lib.id === libraryId,
  );
  const selectedQualityProfile = (qualityProfiles.data ?? []).find(
    (q) => q.id === selectedLibrary?.quality_profile_id,
  );

  // Pre-fill the platform from the lookup candidate when IGDB
  // (or another platform-aware provider) returned a slug. Falls
  // back to the first platform when the candidate has no slug or
  // its slug isn't in the configured Platform table — that keeps
  // the modal submittable for the common single-platform setup.
  useEffect(() => {
    if (platformId !== null) return;
    const list = platforms.data ?? [];
    if (list.length === 0) return;
    const candidateSlug = props.candidate.platformSlug ?? null;
    const matched = candidateSlug
      ? list.find((p) => p.slug === candidateSlug)
      : undefined;
    const fallback = list[0];
    if (matched === undefined && fallback === undefined) return;
    setPlatformId((matched ?? fallback!).id);
  }, [platforms.data, platformId, props.candidate.platformSlug]);

  // Slice 386 — Sonarr-style library picker. Default to the
  // first library so the modal stays one-click for the
  // single-library setup; the operator overrides when they have
  // multiple roots.
  useEffect(() => {
    if (libraryId !== null) return;
    const list = libraries.data ?? [];
    if (list.length === 0) return;
    setLibraryId(list[0]!.id);
  }, [libraries.data, libraryId]);

  function submit(): void {
    if (platformId === null) return;
    add.mutate(
      {
        providerName: props.candidate.providerName,
        providerGameId: props.candidate.providerGameId,
        title: props.candidate.title,
        platformId,
        libraryId: libraryId ?? undefined,
        monitored,
      },
      {
        onSuccess: (game) => {
          pushToast({
            kind: "success",
            title: t("add.successTitle"),
            description: t("add.successBody", { title: game.title }),
          });
          props.onClose();
          navigate(`/game/${game.id}`);
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("add.errorTitle"),
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
      aria-label={t("add.modalTitle", { title: props.candidate.title })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("add.modalTitle", { title: props.candidate.title })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("add.providerSource", {
              provider: props.candidate.providerName,
              id: props.candidate.providerGameId,
            })}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-4 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("add.platformLabel")}
            </span>
            {platforms.isPending ? (
              <p className="text-xs text-zinc-500">{t("add.loadingPlatforms")}</p>
            ) : platforms.isError ? (
              <p className="text-xs text-red-400">{platforms.error.message}</p>
            ) : (platforms.data ?? []).length === 0 ? (
              <p className="text-xs text-amber-400">
                {t("add.noPlatforms")}
              </p>
            ) : (
              <select
                value={platformId ?? ""}
                onChange={(e) => setPlatformId(Number(e.target.value))}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {platforms.data!.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("add.libraryLabel")}
            </span>
            {libraries.isPending ? (
              <p className="text-xs text-zinc-500">{t("add.loadingLibraries")}</p>
            ) : libraries.isError ? (
              <p className="text-xs text-red-400">{libraries.error.message}</p>
            ) : (libraries.data ?? []).length === 0 ? (
              <p className="text-xs text-amber-400">
                {t("add.noLibraries")}
              </p>
            ) : (
              <select
                value={libraryId ?? ""}
                onChange={(e) => setLibraryId(Number(e.target.value))}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {libraries.data!.map((lib) => (
                  <option key={lib.id} value={lib.id}>
                    {lib.name} — {lib.path}
                  </option>
                ))}
              </select>
            )}
          </label>

          {/* Profile cascade — read-only. It follows the library
              binding above; to change it the operator edits the
              library (Settings → Libraries) or its quality
              profile (Settings → Profiles). Shown here so the
              "which rules will gate this game" question is
              answered before the operator hits Add. */}
          <div className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("add.profileLabel")}
            </span>
            <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-sm">
              {selectedQualityProfile ? (
                <>
                  <span className="text-zinc-100">
                    {selectedQualityProfile.name}
                  </span>
                  <span className="ml-2 text-[0.7rem] text-zinc-500">
                    {t("add.profileMinScore", {
                      score: selectedQualityProfile.auto_grab_min_score,
                    })}
                  </span>
                </>
              ) : (
                <span className="text-xs text-zinc-500">
                  {t("add.profileFromLibrary")}
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
              {t("add.monitoredLabel")}
            </span>
          </label>

          <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/40 p-3 text-[0.65rem] text-zinc-500">
            {t("add.refreshHint")}
          </p>

          {add.isError && (
            <p role="alert" className="text-xs text-red-400">
              {add.error.message}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("add.cancel")}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={platformId === null || add.isPending}
            className={[
              "rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900",
              "hover:bg-brand-300",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {add.isPending ? t("add.submitting") : t("add.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
