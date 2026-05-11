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

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useGameMetadata,
  type GameMetadataProvider,
} from "@/lib/api/queries/games";

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
}): ReactElement {
  const { t, i18n } = useTranslation("game");
  const { entry } = props;
  const linkBuilder = PROVIDER_LINKS[entry.providerName];
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
        <h3 className="text-sm font-semibold text-zinc-100">
          {t(
            `metadata.providerName.${entry.providerName}` as never,
            {
              defaultValue: entry.providerName,
            },
          )}
        </h3>
        <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-500">
          {entry.providerGameId && (
            <span className="font-mono">
              id: {entry.providerGameId}
              {linkBuilder && (
                <>
                  {" "}·{" "}
                  <a
                    href={linkBuilder(entry.providerGameId)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand hover:underline"
                  >
                    {t("metadata.open")}
                  </a>
                </>
              )}
            </span>
          )}
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
    </section>
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
            <ProviderCard key={p.providerName} entry={p} />
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
