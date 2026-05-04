/**
 * DAT-sources read hook (slice 267).
 *
 * Wraps ``GET /api/v3/dat-source`` — DAT cache summary grouped
 * by source name (No-Intro / Redump / TOSEC / etc.).
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

export interface DatSourceSummary {
  source: string;
  entry_count: number;
  platform_count: number;
  latest_updated_at: string | null;
}

const KEY = ["settings", "dat-sources"] as const;

export function useDatSources(): UseQueryResult<DatSourceSummary[], ApiError> {
  return useQuery<DatSourceSummary[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<DatSourceSummary[]>("/api/v3/dat-source"),
    staleTime: 5 * 60_000,
  });
}
