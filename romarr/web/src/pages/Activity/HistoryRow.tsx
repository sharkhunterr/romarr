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

import type React from "react";
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
  /** Optional click handler — when set, the row becomes a button
   * that opens a detail sheet on activation. */
  onSelect?: (event: HistoryEvent) => void;
}

export function HistoryRow(props: HistoryRowProps): ReactElement {
  const { event, hideGameLink, i18nNs, locale, onSelect } = props;
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
          to={`/game/${gameId}`}
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

  // Open the detail sheet on click — but only when the click
  // didn't originate from one of the nested links (game title /
  // release) so navigating away still works as before.
  const handleRowClick = (e: React.MouseEvent<HTMLLIElement>): void => {
    if (!onSelect) return;
    const target = e.target as HTMLElement;
    if (target.closest("a")) return;
    onSelect(event);
  };
  const handleRowKey = (e: React.KeyboardEvent<HTMLLIElement>): void => {
    if (!onSelect) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(event);
    }
  };

  return (
    <li
      onClick={onSelect ? handleRowClick : undefined}
      onKeyDown={onSelect ? handleRowKey : undefined}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      className={[
        "flex flex-col gap-1.5 rounded-md",
        "border border-zinc-800 bg-zinc-900/40 px-3 py-2",
        "text-sm",
        onSelect
          ? "cursor-pointer hover:border-zinc-700 hover:bg-zinc-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          : "",
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
      {/* job_run rows ship an ``outputSummary`` dict the runner
          populates (e.g. RssSync → indexers_succeeded / candidates
          / grabs_dispatched / grabs_failed; RescanLibrary →
          total_items / matched / failed). Render the non-null
          numeric entries as a compact ``k: v · k: v`` chip list so
          the row tells the operator what actually happened. */}
      {event.eventType === "job_run" && event.outputSummary && (
        <p className="truncate text-[0.7rem] text-zinc-300">
          {Object.entries(event.outputSummary as Record<string, unknown>)
            .filter(([, v]) => typeof v === "number")
            .map(([k, v], i) => (
              <span key={k}>
                {i > 0 && <span className="text-zinc-600"> · </span>}
                <span className="text-zinc-500">
                  {t(`history.outputSummary.${k}`, { defaultValue: k })}:{" "}
                </span>
                <span className="font-mono">{String(v)}</span>
              </span>
            ))}
        </p>
      )}
      {reason && (
        <p className="truncate text-[0.7rem] text-red-300">
          <span className="text-red-500/70">{t("history.detail.reason")}: </span>
          {(() => {
            // Backend emits ``<code>: <detail>`` (e.g.
            // ``rejected: platform_mismatch`` or
            // ``indexer_failed: auth_error: 401``). Translate the
            // first segment via ``history.noGrabReason.<code>`` and
            // append the rest verbatim so the operator gets both a
            // human label and the raw detail.
            const idx = reason.indexOf(": ");
            const code = idx >= 0 ? reason.slice(0, idx) : reason;
            const tail = idx >= 0 ? reason.slice(idx + 2) : "";
            const label = t(`history.noGrabReason.${code}`, {
              defaultValue: code,
            });
            return tail ? `${label} — ${tail}` : label;
          })()}
        </p>
      )}
    </li>
  );
}
