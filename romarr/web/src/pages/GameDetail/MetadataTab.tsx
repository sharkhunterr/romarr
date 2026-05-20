/**
 * Slice 409 — Game detail Metadata tab.
 *
 * Per-provider snapshot for a game: the FK id Romarr uses to
 * look it up on each provider (IGDB, MobyGames, ScreenScraper,
 * LaunchBox, RetroAchievements), the cached payload the
 * aggregator last pulled (title, summary, genres, cover URL,
 * release date, …), and the per-algo file hashes from every
 * imported Dump on disk.
 *
 * Lets the operator cross-check what each provider knows about
 * the game without poking ``metadata_cache`` by hand.
 */

import { type ReactElement, useState } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useClearProvider,
  useGameMetadata,
  useProviderCandidates,
  useRelinkProvider,
  type GameMetadataProvider,
  type ProviderCandidate,
} from "@/lib/api/queries/games";
import { useToastStore } from "@/lib/store/toast";

const RELINKABLE_PROVIDERS = new Set([
  "igdb",
  "mobygames",
  "screenscraper",
  "launchbox",
  "retroachievements",
]);

const PROVIDER_LINKS: Record<string, (id: string) => string> = {
  igdb: (id) => `https://www.igdb.com/games/${id}`,
  mobygames: (id) => `https://www.mobygames.com/game/${id}`,
  screenscraper: (id) =>
    `https://www.screenscraper.fr/gameinfos.php?gameid=${id}`,
  launchbox: (id) =>
    `https://gamesdb.launchbox-app.com/games/details/${id}`,
  retroachievements: (id) => `https://retroachievements.org/game/${id}`,
};

function ProviderCard(props: {
  entry: GameMetadataProvider;
  gameId: number;
  gameTitle: string;
}): ReactElement {
  const { t, i18n } = useTranslation("game");
  const { entry, gameId, gameTitle } = props;
  const linkBuilder = PROVIDER_LINKS[entry.providerName];
  const [relinkOpen, setRelinkOpen] = useState(false);
  const pushToast = useToastStore((s) => s.push);
  const clearMutation = useClearProvider();
  const canRelink = RELINKABLE_PROVIDERS.has(entry.providerName);
  const onClear = (): void => {
    clearMutation.mutate(
      { gameId, providerName: entry.providerName },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("metadata.relink.toast.clearedTitle"),
            description: t("metadata.relink.toast.clearedBody", {
              provider: entry.providerName,
            }),
          }),
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("metadata.relink.toast.failedTitle"),
            description: err.message,
          }),
      },
    );
  };
  const fetchedAt = entry.fetchedAt
    ? new Date(entry.fetchedAt).toLocaleString(i18n.language)
    : null;
  const expiresAt = entry.expiresAt
    ? new Date(entry.expiresAt).toLocaleString(i18n.language)
    : null;

  // Drop the noisy keys we already render in their own pill, then
  // surface the remainder as a sorted dt/dd list so the operator
  // sees every contribution the provider made.
  const noisy = new Set(["title", "summary"]);
  const fieldEntries = Object.entries(entry.fields ?? {})
    .filter(([k]) => !noisy.has(k))
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-zinc-100">
            {t(
              `metadata.providerName.${entry.providerName}` as never,
              {
                defaultValue: entry.providerName,
              },
            )}
          </h3>
          {canRelink && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setRelinkOpen(true)}
                className={[
                  "rounded border border-zinc-700 px-1.5 py-0.5",
                  "text-[0.6rem] font-medium text-zinc-300",
                  "hover:bg-zinc-800 hover:text-zinc-100",
                ].join(" ")}
              >
                {t("metadata.relink.button")}
              </button>
              {(entry.providerGameId || entry.cachedProviderGameId) && (
                <button
                  type="button"
                  onClick={onClear}
                  disabled={clearMutation.isPending}
                  className={[
                    "rounded border border-zinc-700 px-1.5 py-0.5",
                    "text-[0.6rem] font-medium text-zinc-400",
                    "hover:bg-zinc-800 hover:text-red-300",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  ].join(" ")}
                >
                  {clearMutation.isPending
                    ? t("metadata.relink.clearing")
                    : t("metadata.relink.clear")}
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-500">
          {(() => {
            // ``providerGameId`` is the operator-pinned FK from
            // the Game row. RA doesn't always populate that
            // column on a metadata refresh; the cached row from
            // ``metadata_cache`` always carries the provider's
            // canonical id though, so we fall back to it. Either
            // surfaces the same "open external page" link.
            const id =
              entry.providerGameId ?? entry.cachedProviderGameId ?? null;
            if (id === null) return null;
            return (
              <span className="font-mono">
                id: {id}
                {linkBuilder && (
                  <>
                    {" "}·{" "}
                    <a
                      href={linkBuilder(id)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand hover:underline"
                    >
                      {t("metadata.open")}
                    </a>
                  </>
                )}
              </span>
            );
          })()}
          {fetchedAt && (
            <span>{t("metadata.fetchedAt", { value: fetchedAt })}</span>
          )}
        </div>
      </header>

      {typeof entry.fields["title"] === "string" && (
        <p className="mb-2 text-xs text-zinc-200">
          <span className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
            {t("metadata.fields.title")}:
          </span>{" "}
          {String(entry.fields["title"])}
        </p>
      )}
      {typeof entry.fields["summary"] === "string" && (
        <p className="mb-2 line-clamp-3 text-xs text-zinc-300">
          {String(entry.fields["summary"])}
        </p>
      )}

      {fieldEntries.length === 0 ? (
        <p className="text-[0.7rem] text-zinc-500">
          {entry.fields && Object.keys(entry.fields).length === 0
            ? t("metadata.noCache")
            : null}
        </p>
      ) : (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[0.7rem]">
          {fieldEntries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
                {key}
              </dt>
              <dd className="min-w-0 break-words text-zinc-200">
                {renderValue(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {entry.coverUrl && (
        <p className="mt-2 truncate text-[0.65rem]">
          <a
            href={entry.coverUrl}
            target="_blank"
            rel="noreferrer"
            className="text-brand hover:underline"
          >
            {entry.coverUrl}
          </a>
        </p>
      )}

      {expiresAt && (
        <p className="mt-1 text-[0.6rem] text-zinc-600">
          {t("metadata.expiresAt", { value: expiresAt })}
        </p>
      )}

      {relinkOpen && (
        <RelinkModal
          gameId={gameId}
          gameTitle={gameTitle}
          providerName={entry.providerName}
          currentProviderGameId={
            entry.providerGameId ?? entry.cachedProviderGameId ?? null
          }
          onClose={() => setRelinkOpen(false)}
        />
      )}
    </section>
  );
}

/** Per-provider relink picker. Calls
 * GET /game/{id}/provider/{name}/candidates (which auto-strips the
 * No-Intro tags from the game title) and on pick fires the mutation
 * that pins the FK + wipes cache + force-refreshes. The detail +
 * metadata + list caches are invalidated so the new payload renders
 * without a page reload. */
function RelinkModal(props: {
  gameId: number;
  gameTitle: string;
  providerName: string;
  currentProviderGameId: string | null;
  onClose: () => void;
}): ReactElement {
  const { t } = useTranslation("game");
  const [query, setQuery] = useState("");
  const candidates = useProviderCandidates(
    props.gameId,
    props.providerName,
    query || null,
  );
  const relinkMutation = useRelinkProvider();
  const pushToast = useToastStore((s) => s.push);

  const onPick = (c: ProviderCandidate): void => {
    relinkMutation.mutate(
      {
        gameId: props.gameId,
        providerName: props.providerName,
        providerGameId: c.providerGameId,
      },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("metadata.relink.toast.successTitle"),
            description: t("metadata.relink.toast.successBody", {
              title: c.title,
              provider: props.providerName,
            }),
          });
          props.onClose();
        },
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("metadata.relink.toast.failedTitle"),
            description: err.message,
          }),
      },
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose();
      }}
      className={[
        "fixed inset-0 z-50 flex items-center justify-center",
        "bg-black/60 backdrop-blur-sm p-4",
      ].join(" ")}
    >
      <div
        className={[
          "w-full max-w-2xl rounded-lg border border-zinc-700",
          "bg-zinc-950 shadow-xl",
          "max-h-[85vh] flex flex-col",
        ].join(" ")}
      >
        <header className="flex items-center justify-between gap-3 border-b border-zinc-800 p-4">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100">
              {t("metadata.relink.modal.title", {
                provider: props.providerName,
              })}
            </h3>
            <p className="text-[0.65rem] text-zinc-500">
              {t("metadata.relink.modal.subtitle", { title: props.gameTitle })}
            </p>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded text-zinc-400 hover:text-zinc-100 px-2 py-1"
            aria-label={t("metadata.relink.modal.close")}
          >
            ×
          </button>
        </header>

        <div className="border-b border-zinc-800 p-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("metadata.relink.modal.queryPlaceholder")}
            className={[
              "w-full rounded-md border border-zinc-800 bg-zinc-900",
              "px-3 py-1.5 text-sm text-zinc-100",
              "placeholder:text-zinc-500",
              "focus:outline-none focus:border-brand",
            ].join(" ")}
          />
          {candidates.data?.queriesTried &&
            candidates.data.queriesTried.length > 0 && (
              <p className="mt-1 text-[0.6rem] text-zinc-500">
                {t("metadata.relink.modal.queriesTried", {
                  list: candidates.data.queriesTried.join(", "),
                })}
              </p>
            )}
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {candidates.isPending && (
            <p className="p-4 text-sm text-zinc-500">
              {t("metadata.relink.modal.loading")}
            </p>
          )}
          {candidates.isError && (
            <p className="p-4 text-sm text-red-300">
              {candidates.error.message}
            </p>
          )}
          {candidates.data && candidates.data.candidates.length === 0 && (
            <p className="p-4 text-sm text-zinc-500">
              {t("metadata.relink.modal.empty")}
            </p>
          )}
          {candidates.data && candidates.data.candidates.length > 0 && (
            <ul className="space-y-1">
              {candidates.data.candidates.map((c) => {
                const isCurrent =
                  props.currentProviderGameId !== null &&
                  c.providerGameId === props.currentProviderGameId;
                return (
                  <li key={`${c.providerGameId}-${c.platformSlug ?? ""}`}>
                    <button
                      type="button"
                      onClick={() => onPick(c)}
                      disabled={relinkMutation.isPending}
                      className={[
                        "group flex w-full items-start gap-3 rounded-md",
                        "border border-transparent p-2 text-left",
                        "hover:bg-zinc-900 hover:border-zinc-700",
                        "disabled:opacity-50 disabled:cursor-not-allowed",
                        isCurrent ? "bg-emerald-900/20 border-emerald-700/40" : "",
                      ].join(" ")}
                    >
                      {c.coverUrl && (
                        <img
                          src={c.coverUrl}
                          alt=""
                          loading="lazy"
                          className="h-12 w-9 flex-none rounded object-cover bg-zinc-800"
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-100 truncate">
                            {c.title}
                          </span>
                          {isCurrent && (
                            <span className="text-[0.55rem] text-emerald-300 uppercase">
                              {t("metadata.relink.modal.current")}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-400">
                          <span className="font-mono">#{c.providerGameId}</span>
                          {c.platformName && <span>· {c.platformName}</span>}
                          {c.releaseYear && <span>· {c.releaseYear}</span>}
                          <span className="ml-auto font-mono text-zinc-500">
                            {Math.round(c.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    return value.length === 0 ? "—" : value.map(String).join(", ");
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

interface MetadataTabProps {
  gameId: number;
  /** Game title — passed down so the Relink modal can show it
   * in the header context. */
  gameTitle: string;
}

export function MetadataTab(props: MetadataTabProps): ReactElement {
  const { t } = useTranslation("game");
  const metadata = useGameMetadata(props.gameId);

  if (metadata.isPending) return <ListSkeleton rows={3} />;
  if (metadata.isError) {
    return (
      <EmptyState
        title={t("metadata.loadError")}
        description={metadata.error.message}
      />
    );
  }

  const data = metadata.data;
  const hashAlgos = Object.keys(data.fileHashes);
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-sm font-medium text-zinc-100">
          {t("metadata.title")}
        </h2>
        <p className="text-[0.65rem] text-zinc-500">
          {t("metadata.subtitle")}
        </p>
      </header>

      {data.providers.length === 0 ? (
        <EmptyState
          title={t("metadata.empty.title")}
          description={t("metadata.empty.body")}
        />
      ) : (
        <div className="space-y-3">
          {data.providers.map((p) => (
            <ProviderCard
              key={p.providerName}
              entry={p}
              gameId={props.gameId}
              gameTitle={props.gameTitle}
            />
          ))}
        </div>
      )}

      {hashAlgos.length > 0 && (
        <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
          <header className="mb-2">
            <h3 className="text-sm font-semibold text-zinc-100">
              {t("metadata.hashes.title")}
            </h3>
            <p className="text-[0.65rem] text-zinc-500">
              {t("metadata.hashes.subtitle")}
            </p>
          </header>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[0.7rem]">
            {hashAlgos.map((algo) => (
              <div key={algo} className="contents">
                <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
                  {algo}
                </dt>
                <dd className="min-w-0">
                  <ul className="space-y-0.5">
                    {data.fileHashes[algo]!.map((h) => (
                      <li
                        key={h}
                        className="break-all font-mono text-[0.65rem] text-zinc-200"
                      >
                        {h}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
