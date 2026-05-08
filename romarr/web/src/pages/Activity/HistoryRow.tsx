/**
 * Detailed history row (slice 363).
 *
 * Shared between Activity → History and the per-game History
 * tab. Renders every operator-relevant field the backend now
 * ships on each event:
 *
 *   * label (event type — Manual grab / RSS sync / Import / …)
 *   * subject — game name (clickable link to its detail page) +
 *     release id when present
 *   * dates — start / end / duration
 *   * status — green OK / red FAIL pill
 *   * reason — red line when filled
 *   * search-only: query string + chosen indexer guid + score
 *   * import-only: dest_path basename + download client name +
 *     imported via (webhook / watcher / manual)
 */

import { type ReactElement } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { components } from "@/types/api/schema";

type HistoryEvent = components["schemas"]["HistoryEvent"];

function _formatDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale);
}

function _formatDuration(
  ms: number | null | undefined,
  t: (k: string, opts?: Record<string, unknown>) => string,
): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return t("history.duration.ms", { ms });
  const s = ms / 1000;
  if (s < 60) return t("history.duration.s", { s: s.toFixed(1) });
  const m = s / 60;
  if (m < 60) return t("history.duration.m", { m: m.toFixed(1) });
  const h = m / 60;
  return t("history.duration.h", { h: h.toFixed(1) });
}

interface HistoryRowProps {
  event: HistoryEvent;
  /** When set, hide the game-link (e.g. on the per-game History tab
   * where every row is for the same game). */
  hideGameLink?: boolean;
  /** Translation namespace — ``activity`` for the global feed,
   * ``game`` for the per-game tab. */
  i18nNs: "activity" | "game";
  /** ``i18n.language`` — passed in so callers control the locale. */
  locale: string;
}

export function HistoryRow(props: HistoryRowProps): ReactElement {
  const { event, hideGameLink, i18nNs, locale } = props;
  const { t } = useTranslation(i18nNs);

  const summary = event.summary;
  const reason = event.reason;
  const isSearch = event.eventType === "search";
  const isImport = event.eventType === "import";

  // Header label: Manual grab / RSS sync / Import / Job …
  const labelKey =
    isSearch && summary
      ? `history.searchType.${summary}`
      : `history.eventLabel.${event.eventType}`;
  const eventLabel = t(labelKey, { defaultValue: event.eventType });

  // Subject line: game title (linked) + release id when known.
  const gameTitle = event.gameTitle;
  const gameId = event.gameId;
  const releaseId = event.releaseId;
  const subject = (() => {
    if (gameTitle && gameId && !hideGameLink) {
      return (
        <Link
          to={`/games/${gameId}`}
          className="truncate text-zinc-100 hover:text-brand hover:underline"
        >
          {gameTitle}
        </Link>
      );
    }
    if (gameTitle) {
      return <span className="truncate text-zinc-100">{gameTitle}</span>;
    }
    if (gameId) {
      return (
        <span className="truncate text-zinc-300">
          {t("history.subjectGame", { id: gameId, defaultValue: `Game #${gameId}` })}
        </span>
      );
    }
    if (releaseId) {
      return (
        <span className="truncate text-zinc-300">
          {t("history.subjectRelease", { id: releaseId })}
        </span>
      );
    }
    return (
      <span className="truncate text-zinc-500">
        {t("history.subjectEvent", {
          id: event.id,
          defaultValue: `event #${event.id}`,
        })}
      </span>
    );
  })();

  const duration = _formatDuration(event.durationMs ?? null, t);

  return (
    <li
      className={[
        "flex flex-col gap-1.5 rounded-md",
        "border border-zinc-800 bg-zinc-900/40 px-3 py-2",
        "text-sm",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="flex items-center gap-2 truncate">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-zinc-500">
              {eventLabel}
            </span>
            {subject}
          </p>
          <p className="truncate text-[0.65rem] text-zinc-500">
            {_formatDate(event.date, locale)}
            {event.finishedAt && (
              <>
                {" → "}
                {_formatDate(event.finishedAt, locale)}
              </>
            )}
            {duration && (
              <>
                {" · "}
                <span className="font-mono">{duration}</span>
              </>
            )}
          </p>
        </div>
        <span
          className={[
            "shrink-0 rounded-full px-2 py-0.5",
            "text-[0.65rem] font-medium ring-1 ring-inset",
            event.successful
              ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
              : "bg-red-700/30 text-red-200 ring-red-500/40",
          ].join(" ")}
        >
          {event.successful ? t("history.statusOk") : t("history.statusFailed")}
        </span>
      </div>

      {/* Detail rows below the header — only render the slots
          that have content so a sparse row stays compact. */}
      {isSearch && event.query && (
        <p className="truncate text-[0.7rem] text-zinc-300">
          <span className="text-zinc-500">{t("history.detail.query")}: </span>
          <span className="font-mono">{event.query}</span>
        </p>
      )}
      {isSearch && event.score !== null && event.score !== undefined && (
        <p className="text-[0.7rem] text-zinc-300">
          <span className="text-zinc-500">{t("history.detail.score")}: </span>
          <span className="font-mono">{event.score}</span>
        </p>
      )}
      {isSearch && event.chosenIndexerGuid && (
        <p className="truncate text-[0.7rem] text-zinc-400">
          <span className="text-zinc-500">{t("history.detail.guid")}: </span>
          <span className="font-mono">
            {event.chosenIndexerGuid.length > 80
              ? `${event.chosenIndexerGuid.slice(0, 77)}…`
              : event.chosenIndexerGuid}
          </span>
        </p>
      )}
      {isImport && event.destPath && (
        <p className="truncate text-[0.7rem] text-zinc-300">
          <span className="text-zinc-500">{t("history.detail.dest")}: </span>
          <span className="font-mono">{event.destPath}</span>
        </p>
      )}
      {isImport && summary && (
        <p className="truncate text-[0.7rem] text-zinc-400">
          <span className="text-zinc-500">{t("history.detail.source")}: </span>
          <span className="font-mono">{summary}</span>
        </p>
      )}
      {(isImport || isSearch) && event.downloadClientName && (
        <p className="truncate text-[0.7rem] text-zinc-300">
          <span className="text-zinc-500">{t("history.detail.client")}: </span>
          {event.downloadClientName}
        </p>
      )}
      {isImport && event.importedVia && (
        <p className="truncate text-[0.7rem] text-zinc-400">
          <span className="text-zinc-500">{t("history.detail.via")}: </span>
          {t(`history.importedVia.${event.importedVia}`, {
            defaultValue: event.importedVia,
          })}
        </p>
      )}
      {reason && (
        <p className="truncate text-[0.7rem] text-red-300">
          <span className="text-red-500/70">{t("history.detail.reason")}: </span>
          {reason}
        </p>
      )}
    </li>
  );
}
