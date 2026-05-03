/**
 * Metadata-lookup hook (slice 144).
 *
 * Wraps `GET /api/v3/game/lookup` — admin-only aggregated
 * search across every enabled metadata provider. Returns a
 * confidence-ranked list of provider candidates the operator
 * can pick from on the AddNew page.
 *
 * The hook is gated on `q.length > 0` so an empty input
 * doesn't fire a search round on every keystroke.
 */

import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type GameLookupRow = components["schemas"]["GameLookupRow"];

export interface LookupParams {
  q: string;
  platformSlug?: string;
  limit?: number;
}

export function useGameLookup(
  params: LookupParams,
): UseQueryResult<GameLookupRow[], ApiError> {
  const search = new URLSearchParams();
  search.set("q", params.q);
  if (params.platformSlug) search.set("platformSlug", params.platformSlug);
  if (params.limit !== undefined) search.set("limit", String(params.limit));

  return useQuery<GameLookupRow[], ApiError>({
    queryKey: ["metadata", "lookup", params],
    queryFn: () =>
      apiFetch<GameLookupRow[]>(`/api/v3/game/lookup?${search.toString()}`),
    enabled: params.q.trim().length > 0,
    // Each round goes to live indexers; cache briefly so the
    // operator can scroll the result list without re-firing.
    staleTime: 30_000,
  });
}
