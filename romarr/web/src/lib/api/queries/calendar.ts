/**
 * Calendar TanStack Query hook (T104).
 *
 * Wraps GET /api/v3/calendar (spec 013 slice 36). The MVP
 * endpoint returns []; the shape is pinned so this hook
 * doesn't need to change once a real preservation-event
 * source is wired up.
 *
 * Note: the Calendar page is intentionally NOT linked from
 * the primary nav per operator feedback — Romarr targets
 * decades-old ROMs with no upcoming-release calendar to
 * surface. Page is reachable by direct URL only and kept
 * in case a future homebrew / translation calendar source
 * lands.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type CalendarEvent = components["schemas"]["CalendarEvent"];

export interface CalendarRange {
  /** ISO-8601 datetime string; inclusive lower bound. */
  start: string;
  /** ISO-8601 datetime string; exclusive upper bound. */
  end: string;
}

export function useCalendar(
  range: CalendarRange,
): UseQueryResult<CalendarEvent[], ApiError> {
  return useQuery<CalendarEvent[], ApiError>({
    queryKey: ["calendar", range.start, range.end],
    queryFn: () => {
      const params = new URLSearchParams({
        start: range.start,
        end: range.end,
      });
      return apiFetch<CalendarEvent[]>(`/api/v3/calendar?${params.toString()}`);
    },
    staleTime: 60_000,
  });
}
