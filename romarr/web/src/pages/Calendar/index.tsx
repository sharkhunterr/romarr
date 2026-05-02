/**
 * Calendar page (P-CAL, T104).
 *
 * Month-view skeleton over /api/v3/calendar. The MVP endpoint
 * returns []; the page renders a graceful EmptyState in that
 * case and a per-event card list when a future preservation-
 * event source lands.
 *
 * Intentionally NOT linked from the bottom nav per operator
 * feedback: Romarr targets decades-old ROMs with no upcoming-
 * release calendar to surface. The page is reachable by direct
 * URL only and kept in case a future homebrew / translation
 * calendar source is wired up.
 *
 * Strings resolve through the `calendar` namespace
 * (slice 70). The localized month name comes from
 * `Intl.DateTimeFormat` honoring the active i18next locale.
 */

import { useMemo, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useCalendar,
  type CalendarEvent,
} from "@/lib/api/queries/calendar";

function monthBounds(year: number, month: number): {
  start: string;
  end: string;
} {
  const start = new Date(Date.UTC(year, month, 1));
  const end = new Date(Date.UTC(year, month + 1, 1));
  return { start: start.toISOString(), end: end.toISOString() };
}

function MonthHeader(props: {
  year: number;
  month: number;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}): ReactElement {
  const { t, i18n } = useTranslation("calendar");
  const monthName = new Date(Date.UTC(props.year, props.month, 1))
    .toLocaleDateString(i18n.resolvedLanguage ?? "en", {
      year: "numeric",
      month: "long",
      timeZone: "UTC",
    });
  return (
    <div className="mb-4 flex items-center justify-between gap-2">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={props.onPrev}
          aria-label={t("nav.previous")}
          className="rounded-md px-2 py-1 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          ←
        </button>
        <button
          type="button"
          onClick={props.onToday}
          className="rounded-md px-2 py-1 text-xs font-medium text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("nav.today")}
        </button>
        <button
          type="button"
          onClick={props.onNext}
          aria-label={t("nav.next")}
          className="rounded-md px-2 py-1 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          →
        </button>
      </div>
      <h2 className="font-mono text-sm font-medium text-zinc-300">
        {monthName}
      </h2>
    </div>
  );
}

function EventCard(props: { event: CalendarEvent }): ReactElement {
  const { t } = useTranslation("calendar");
  const { event } = props;
  const kindLabel = t(`kind.${event.kind}`, { defaultValue: event.kind });
  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-100">
            {event.title}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {event.releaseDate} · {kindLabel}
          </p>
        </div>
        {event.monitored && (
          <span
            aria-label={t("monitoredAria")}
            className="rounded-full bg-brand/20 px-2 py-0.5 text-[0.6rem] font-medium uppercase tracking-wider text-brand"
          >
            ★
          </span>
        )}
      </div>
      {event.summary && (
        <p className="mt-2 text-xs text-zinc-400">{event.summary}</p>
      )}
    </li>
  );
}

export function CalendarPage(): ReactElement {
  const { t } = useTranslation("calendar");
  const today = new Date();
  const [{ year, month }, setCursor] = useState({
    year: today.getUTCFullYear(),
    month: today.getUTCMonth(),
  });

  const range = useMemo(() => monthBounds(year, month), [year, month]);
  const calendar = useCalendar(range);

  function shift(delta: number): void {
    setCursor((prev) => {
      const nextMonth = prev.month + delta;
      const nextYear = prev.year + Math.floor(nextMonth / 12);
      const normalized = ((nextMonth % 12) + 12) % 12;
      return { year: nextYear, month: normalized };
    });
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
      </header>

      <MonthHeader
        year={year}
        month={month}
        onPrev={() => shift(-1)}
        onNext={() => shift(1)}
        onToday={() =>
          setCursor({
            year: today.getUTCFullYear(),
            month: today.getUTCMonth(),
          })
        }
      />

      {calendar.isLoading && <ListSkeleton rows={3} />}

      {calendar.isError && (
        <EmptyState
          title={t("loadError")}
          description={calendar.error.message}
        />
      )}

      {calendar.isSuccess && calendar.data.length === 0 && (
        <EmptyState
          title={t("empty.title")}
          description={t("empty.body")}
        />
      )}

      {calendar.isSuccess && calendar.data.length > 0 && (
        <ul className="space-y-2">
          {calendar.data.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </ul>
      )}
    </div>
  );
}
