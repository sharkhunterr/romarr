/**
 * Per-game grouped timeline (slice 467 / Lot 3).
 *
 * Renders the same flat list of HistoryEvent as ``HistoryTab``
 * used to, but visually groups events that happened within
 * ``SESSION_GAP_MS`` of each other into "sessions" — the
 * search → grab → download → import chain typically completes
 * inside that window, so this surfaces the chain naturally
 * without a server-side correlation join.
 *
 * Sessions:
 *   * Header — date of the first event in the session, in the
 *     viewer's locale.
 *   * Body — each event rendered via ``HistoryRow`` (so the
 *     Lot 1 card design carries through), but stacked with a
 *     left-side vertical connector that ties them together.
 *   * Gap — a faint divider between sessions makes the
 *     transition obvious without a heavy separator.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/types/api/schema";

import { HistoryRow } from "@/pages/Activity/HistoryRow";

type HistoryEvent = components["schemas"]["HistoryEvent"];

// Events with a smaller delta than this collapse into one session.
// 30 min is long enough to span a search → torrent-download →
// import cycle for big meta-torrents (Minerva packs) but short
// enough that the operator's mental "I grabbed this thing one
// afternoon" boundary stays correct.
const SESSION_GAP_MS = 30 * 60 * 1000;

interface Session {
  /** First event's date — the session header label. */
  startedAt: string;
  events: HistoryEvent[];
}

function groupIntoSessions(events: HistoryEvent[]): Session[] {
  // ``events`` arrives sorted ``date DESC`` from the backend.
  // Walk from newest to oldest, opening a new session whenever
  // the gap to the previous event exceeds ``SESSION_GAP_MS``.
  const sessions: Session[] = [];
  let current: Session | null = null;
  let prevTime: number | null = null;

  for (const event of events) {
    const t = new Date(event.date).getTime();
    if (
      current === null ||
      prevTime === null ||
      // ``prev - t`` because events are newest-first (DESC).
      prevTime - t > SESSION_GAP_MS
    ) {
      current = { startedAt: event.date, events: [event] };
      sessions.push(current);
    } else {
      current.events.push(event);
    }
    prevTime = t;
  }
  return sessions;
}

function formatSessionHeader(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface HistoryTimelineProps {
  events: HistoryEvent[];
  locale: string;
  i18nNs: "activity" | "game";
}

export function HistoryTimeline(props: HistoryTimelineProps): ReactElement {
  const { events, locale, i18nNs } = props;
  const { t } = useTranslation(i18nNs);
  const sessions = groupIntoSessions(events);

  return (
    <div className="space-y-5">
      {sessions.map((session, idx) => (
        <section
          key={`${session.startedAt}-${idx}`}
          aria-label={t("history.session.ariaLabel", {
            defaultValue: "Activity session",
          })}
        >
          {/* Session header — date of the most-recent event in
              the session. Provides a clear visual divider AND
              tells the operator at a glance when this batch of
              activity happened. */}
          <header className="mb-2 flex items-center gap-3">
            <span className="text-[0.7rem] font-semibold uppercase tracking-wider text-zinc-400">
              {formatSessionHeader(session.startedAt, locale)}
            </span>
            <span className="text-[0.6rem] text-zinc-600">
              {t("history.session.eventCount", {
                count: session.events.length,
                defaultValue: `${session.events.length} event${session.events.length === 1 ? "" : "s"}`,
              })}
            </span>
            <span className="h-px flex-1 bg-zinc-800" />
          </header>
          {/* Session body — events stacked with a left-side
              connector. The wrapping div carries the connector
              line so it remains continuous between rows. */}
          <div className="relative space-y-2 pl-4">
            <span
              aria-hidden="true"
              className="absolute bottom-1 left-1 top-1 w-px bg-zinc-800"
            />
            {session.events.map((event) => (
              <HistoryRow
                key={`${event.eventType}-${event.id}`}
                event={event}
                i18nNs={i18nNs}
                locale={locale}
                hideGameLink
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
