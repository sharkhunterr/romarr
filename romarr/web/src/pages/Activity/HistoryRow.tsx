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

// Human-readable byte size — KB/MB/GB/TB binary units. Used for
// the imported-file size cell in the timeline. Returns null when
// the underlying field is absent so the caller can omit the row.
function _formatSize(bytes: number | null | undefined): string | null {
  if (bytes === null || bytes === undefined || bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  // 1 decimal place for sub-100 values, integer otherwise — matches
  // what most file managers / qBit show.
  return value >= 100 ? `${Math.round(value)} ${units[i]}` : `${value.toFixed(1)} ${units[i]}`;
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

// Per event-type pill colors. Lets the operator scan a long feed
// and tell apart search (blue) / import (violet) / job (amber) at
// a glance — before this, every row's label was the same neutral
// grey and only the success/fail pill on the right carried color.
// Search subtypes (cutoff / missing / auto / rss / manual) all
// share the search palette since they're conceptually the same
// operation triggered by different schedulers.
function _eventTypePillClasses(eventType: string): string {
  switch (eventType) {
    case "import":
      return "bg-violet-700/25 text-violet-200 ring-violet-500/40";
    case "search":
      return "bg-sky-700/25 text-sky-200 ring-sky-500/40";
    case "job_run":
      return "bg-amber-700/25 text-amber-200 ring-amber-500/40";
    default:
      return "bg-zinc-700/30 text-zinc-300 ring-zinc-500/40";
  }
}

// Matching solid border colours for the card's left edge. Pairs
// with the pill above so the same hue carries the event type
// through the whole row — a thicker accent than the pill alone,
// readable when the row is dense with detail lines.
function _eventTypeBorderClasses(eventType: string): string {
  switch (eventType) {
    case "import":
      return "border-l-violet-500/70";
    case "search":
      return "border-l-sky-500/70";
    case "job_run":
      return "border-l-amber-500/70";
    default:
      return "border-l-zinc-600";
  }
}

interface DetailItemProps {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
  truncate?: boolean;
}

function DetailItem({
  label,
  children,
  mono = false,
  truncate = false,
}: DetailItemProps): ReactElement {
  return (
    <div className={truncate ? "min-w-0" : undefined}>
      <div className="text-[0.6rem] uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      <div
        className={[
          "text-[0.75rem] text-zinc-200",
          mono ? "font-mono" : "",
          truncate ? "truncate" : "",
        ].join(" ")}
      >
        {children}
      </div>
    </div>
  );
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
  // Fallback chain when no game is bound — never let the row
  // collapse to a bare ``event #N`` since that's useless. The
  // backend ships a meaningful ``summary`` field for every shape:
  //   * job_run    → ``summary`` = job runner name (e.g. "RssSync")
  //   * search row → ``summary`` = search_type ("manual", "rss"…)
  //                   AND ``query`` = what was actually searched
  //   * import row → ``summary`` = source filename
  // Use those before falling back to the bare event id.
  const gameTitle = event.gameTitle;
  const gameId = event.gameId;
  const releaseId = event.releaseId;
  const isJob = event.eventType === "job_run";
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
    // Job rows: prefer the runner name (it's the operator-visible
    // job they actually triggered or scheduled, e.g. "RssSync").
    if (isJob && summary) {
      return (
        <span className="truncate text-zinc-200">
          {t(`history.jobLabel.${summary}`, { defaultValue: summary })}
        </span>
      );
    }
    // Search rows with no monitored-game match: show the raw query
    // the operator typed. Tells them "this search returned nothing
    // useful" instead of an opaque "event #N".
    if (isSearch && event.query) {
      return (
        <span className="truncate text-zinc-200">
          {t("history.subjectQuery", {
            query: event.query,
            defaultValue: `"${event.query}"`,
          })}
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

  // Compute reason label early so we can render the failure
  // banner without a second IIFE buried in JSX.
  const reasonRendered = (() => {
    if (!reason) return null;
    // Backend emits ``<code>: <detail>`` (e.g.
    // ``rejected: platform_mismatch`` or ``indexer_failed: auth_error: 401``).
    // Translate the first segment via ``history.noGrabReason.<code>`` and
    // append the rest verbatim so the operator gets both a human label
    // and the raw detail.
    const idx = reason.indexOf(": ");
    const code = idx >= 0 ? reason.slice(0, idx) : reason;
    const tail = idx >= 0 ? reason.slice(idx + 2) : "";
    const label = t(`history.noGrabReason.${code}`, { defaultValue: code });
    return tail ? `${label} — ${tail}` : label;
  })();

  return (
    <li
      onClick={onSelect ? handleRowClick : undefined}
      onKeyDown={onSelect ? handleRowKey : undefined}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      className={[
        // Card layout: rounded, left border colored per event type
        // so the same hue carries through label + border + accents.
        "flex flex-col gap-2.5 rounded-md",
        "border border-zinc-800 bg-zinc-900/40",
        "border-l-4",
        _eventTypeBorderClasses(event.eventType),
        "px-3.5 py-2.5",
        "text-sm",
        onSelect
          ? "cursor-pointer hover:border-zinc-700 hover:bg-zinc-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          : "",
      ].join(" ")}
    >
      {/* Header: event-type badge + subject (game) + status pill. */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="flex items-center gap-2 truncate">
            <span
              className={[
                "shrink-0 rounded-full px-2 py-0.5",
                "font-mono text-[0.6rem] uppercase tracking-wider",
                "ring-1 ring-inset",
                _eventTypePillClasses(event.eventType),
              ].join(" ")}
            >
              {eventLabel}
            </span>
            <span className="truncate text-[0.95rem] font-medium">
              {subject}
            </span>
          </p>
          <p className="truncate text-[0.7rem] text-zinc-400">
            <span className="font-mono">{_formatDate(event.date, locale)}</span>
            {event.finishedAt && (
              <>
                <span className="mx-1 text-zinc-600">→</span>
                <span className="font-mono">
                  {_formatDate(event.finishedAt, locale)}
                </span>
              </>
            )}
            {duration && (
              <>
                <span className="mx-1.5 text-zinc-600">·</span>
                <span className="font-mono text-zinc-300">{duration}</span>
              </>
            )}
          </p>
        </div>
        <span
          className={[
            "shrink-0 rounded-full px-2.5 py-0.5",
            "text-[0.65rem] font-semibold uppercase tracking-wider",
            "ring-1 ring-inset",
            event.successful
              ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
              : "bg-red-700/30 text-red-200 ring-red-500/40",
          ].join(" ")}
        >
          {event.successful ? t("history.statusOk") : t("history.statusFailed")}
        </span>
      </div>

      {/* Detail grid: 1 col mobile, 2 cols desktop. Only render
          the slots that have content so a sparse row stays
          compact. */}
      <div className="grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {isSearch && event.query && (
          <DetailItem label={t("history.detail.query")} mono truncate>
            {event.query}
          </DetailItem>
        )}
        {isSearch && event.score !== null && event.score !== undefined && (
          <DetailItem label={t("history.detail.score")} mono>
            {event.score}
          </DetailItem>
        )}
        {isSearch && event.chosenIndexerGuid && (
          <DetailItem
            label={t("history.detail.guid")}
            mono
            truncate
          >
            {event.chosenIndexerGuid.length > 80
              ? `${event.chosenIndexerGuid.slice(0, 77)}…`
              : event.chosenIndexerGuid}
          </DetailItem>
        )}
        {(isImport || isSearch) && event.downloadClientName && (
          <DetailItem label={t("history.detail.client")} truncate>
            {event.downloadClientName}
          </DetailItem>
        )}
        {isImport && _formatSize(event.sizeBytes) && (
          <DetailItem label={t("history.detail.size")} mono>
            {_formatSize(event.sizeBytes)}
          </DetailItem>
        )}
        {isImport && summary && (
          <DetailItem
            label={t("history.detail.source")}
            mono
            truncate
          >
            {summary}
          </DetailItem>
        )}
        {isImport && event.destPath && (
          <DetailItem
            label={t("history.detail.dest")}
            mono
            truncate
          >
            {event.destPath}
          </DetailItem>
        )}
        {isImport && event.importedVia && (
          <DetailItem label={t("history.detail.via")}>
            {t(`history.importedVia.${event.importedVia}`, {
              defaultValue: event.importedVia,
            })}
          </DetailItem>
        )}
        {/* job_run rows ship an ``outputSummary`` dict the runner
            populates (e.g. RssSync → indexers_succeeded / candidates
            / grabs_dispatched / grabs_failed / no_grab_reason).
            Render both numeric AND non-empty string entries so
            diagnostic fields like ``no_grab_reason`` reach the
            operator (without them, "GRABS: 0" is silent about why). */}
        {event.eventType === "job_run" &&
          event.outputSummary &&
          Object.entries(event.outputSummary as Record<string, unknown>)
            .filter(
              ([, v]) =>
                typeof v === "number" ||
                (typeof v === "string" && v.length > 0),
            )
            .map(([k, v]) => (
              <DetailItem
                key={k}
                label={t(`history.outputSummary.${k}`, { defaultValue: k })}
                mono
              >
                {String(v)}
              </DetailItem>
            ))}
      </div>

      {/* Failure banner — full-width red strip below the grid so
          the reason can't be missed. */}
      {reasonRendered && (
        <div className="rounded border border-red-700/40 bg-red-950/30 px-2.5 py-1.5">
          <div className="text-[0.6rem] uppercase tracking-wider text-red-400/80">
            {t("history.detail.reason")}
          </div>
          <div className="break-words text-[0.75rem] text-red-200">
            {reasonRendered}
          </div>
        </div>
      )}
    </li>
  );
}
