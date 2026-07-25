/**
 * Manual-match modal for an unidentified-dump row (slice 87).
 *
 * Two-step flow:
 *   1. Search games by title → pick one.
 *   2. Pick a Release → submit.
 *
 * On submit: POST /api/v3/rom/unidentified/{id}/match. Success
 * pushes a toast and closes the modal; the parent page's list
 * refetches automatically because `useMatchUnidentified`
 * invalidates the unidentified query key.
 */

import { useEffect, useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useGames, useReleasesForGame, type Game } from "@/lib/api/queries/games";
import {
  useMatchUnidentified,
  type UnidentifiedDump,
} from "@/lib/api/queries/unidentified";
import { useToastStore } from "@/lib/store/toast";

interface MatchModalProps {
  unidentified: UnidentifiedDump;
  onClose: () => void;
}

export function MatchModal(props: MatchModalProps): ReactElement {
  const { t } = useTranslation("settings");
  const pushToast = useToastStore((s) => s.push);
  const match = useMatchUnidentified();

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [selectedReleaseId, setSelectedReleaseId] = useState<number | null>(null);

  // Debounce query → 200 ms before triggering the games query.
  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query.trim()), 200);
    return () => window.clearTimeout(handle);
  }, [query]);

  const games = useGames(
    debouncedQuery.length > 0 ? { q: debouncedQuery, limit: 25 } : {},
  );
  const releases = useReleasesForGame(selectedGame?.id ?? null);

  const filename = useMemo(() => {
    const path = props.unidentified.path;
    const idx = path.lastIndexOf("/");
    return idx >= 0 ? path.slice(idx + 1) : path;
  }, [props.unidentified.path]);

  function submit(): void {
    if (selectedGame === null || selectedReleaseId === null) return;
    const releaseObj = releases.data?.find((r) => r.id === selectedReleaseId);
    match.mutate(
      {
        id: props.unidentified.id,
        payload: {
          game_id: selectedGame.id,
          release_id: selectedReleaseId,
        },
      },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("unidentified.match.successTitle"),
            description: t("unidentified.match.successBody", {
              filename,
              game: selectedGame.title,
              release: releaseObj?.name ?? `#${selectedReleaseId}`,
            }),
          });
          props.onClose();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("unidentified.match.successTitle"),
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
      aria-label={t("unidentified.match.modalTitle", { filename })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 overflow-y-auto py-[4vh] sm:items-center backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-2xl flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("unidentified.match.modalTitle", { filename })}
          </h2>
        </header>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-4">
          {selectedGame === null ? (
            <Step1
              query={query}
              setQuery={setQuery}
              games={games.data ?? []}
              isLoading={games.isLoading}
              onPick={(g) => {
                setSelectedGame(g);
                setSelectedReleaseId(null);
              }}
            />
          ) : (
            <Step2
              game={selectedGame}
              releases={releases.data ?? []}
              isLoading={releases.isLoading}
              selectedReleaseId={selectedReleaseId}
              setSelectedReleaseId={setSelectedReleaseId}
              onBack={() => {
                setSelectedGame(null);
                setSelectedReleaseId(null);
              }}
            />
          )}

          {match.isError && (
            <p role="alert" className="text-xs text-red-400">
              {match.error?.message}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("unidentified.match.cancel")}
          </button>
          {selectedGame !== null && (
            <button
              type="button"
              onClick={submit}
              disabled={
                selectedReleaseId === null || match.isPending
              }
              className={[
                "rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900",
                "hover:bg-brand-300",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {match.isPending
                ? t("unidentified.match.submitting")
                : t("unidentified.match.submit")}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

interface Step1Props {
  query: string;
  setQuery: (q: string) => void;
  games: Game[];
  isLoading: boolean;
  onPick: (game: Game) => void;
}

function Step1(props: Step1Props): ReactElement {
  const { t } = useTranslation("settings");
  return (
    <section className="space-y-3">
      <p className="text-xs uppercase tracking-widest text-zinc-500">
        {t("unidentified.match.step1")}
      </p>
      <input
        type="text"
        value={props.query}
        onChange={(e) => props.setQuery(e.target.value)}
        placeholder={t("unidentified.match.searchPlaceholder")}
        autoFocus
        className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      />
      {props.query.trim().length === 0 ? (
        <p className="text-xs text-zinc-500">
          {t("unidentified.match.typeToSearch")}
        </p>
      ) : props.games.length === 0 && !props.isLoading ? (
        <p className="text-xs text-zinc-500">
          {t("unidentified.match.noResults", { q: props.query.trim() })}
        </p>
      ) : (
        <ul className="max-h-[40vh] space-y-1 overflow-y-auto">
          {props.games.map((game) => (
            <li key={game.id}>
              <button
                type="button"
                onClick={() => props.onPick(game)}
                className="flex w-full items-center justify-between rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-left hover:border-brand/40 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <span className="truncate text-sm text-zinc-100">
                  {game.title}
                </span>
                <span className="font-mono text-[0.6rem] text-zinc-500">
                  #{game.id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface Step2Props {
  game: Game;
  releases: { id: number; name: string }[];
  isLoading: boolean;
  selectedReleaseId: number | null;
  setSelectedReleaseId: (id: number) => void;
  onBack: () => void;
}

function Step2(props: Step2Props): ReactElement {
  const { t } = useTranslation("settings");
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-widest text-zinc-500">
          {t("unidentified.match.step2")}
        </p>
        <button
          type="button"
          onClick={props.onBack}
          className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-300 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          ← {t("unidentified.match.back")}
        </button>
      </div>
      <p className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-100">
        {props.game.title}
      </p>
      {props.releases.length === 0 && !props.isLoading ? (
        <p className="text-xs text-zinc-500">
          {t("unidentified.match.noReleases")}
        </p>
      ) : (
        <ul className="max-h-[40vh] space-y-1 overflow-y-auto">
          {props.releases.map((release) => {
            const active = props.selectedReleaseId === release.id;
            return (
              <li key={release.id}>
                <button
                  type="button"
                  onClick={() => props.setSelectedReleaseId(release.id)}
                  aria-pressed={active}
                  className={[
                    "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left",
                    active
                      ? "border-brand bg-brand/10 text-zinc-100"
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-300 hover:border-brand/40 hover:bg-zinc-900",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                  ].join(" ")}
                >
                  <span className="truncate text-sm">{release.name}</span>
                  <span className="font-mono text-[0.6rem] text-zinc-500">
                    #{release.id}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
