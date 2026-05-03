/**
 * Game + Release read TanStack Query hooks (slice 87).
 *
 * Wraps the spec 008/014 /api/v3/game read surface (slice 86):
 *   * GET /api/v3/game?q=...&platform_id=...&limit=...
 *   * GET /api/v3/game/{game_id}
 *   * GET /api/v3/game/{game_id}/release
 *
 * Drives the manual-match Game / Release picker. The list
 * hook accepts a debounced query string; consumers debounce
 * upstream (typically via a 200ms timer in the input handler)
 * so we don't pollute the query cache with every keystroke.
 */

import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type Game = components["schemas"]["GameRead"];
export type Release = components["schemas"]["ReleaseRead"];
export type Dump = components["schemas"]["DumpRead"];

export interface ListGamesParams {
  q?: string;
  platformId?: number;
  limit?: number;
}

export function useGames(
  params: ListGamesParams = {},
): UseQueryResult<Game[], ApiError> {
  const search = new URLSearchParams();
  if (params.q !== undefined && params.q.trim()) {
    search.set("q", params.q.trim());
  }
  if (params.platformId !== undefined) {
    search.set("platform_id", String(params.platformId));
  }
  if (params.limit !== undefined) {
    search.set("limit", String(params.limit));
  }
  const qs = search.toString();
  const url = qs ? `/api/v3/game?${qs}` : "/api/v3/game";

  return useQuery<Game[], ApiError>({
    queryKey: ["games", "list", params.q ?? "", params.platformId ?? null, params.limit ?? null],
    queryFn: () => apiFetch<Game[]>(url),
    staleTime: 30_000,
  });
}

export function useGame(
  gameId: number | null,
): UseQueryResult<Game, ApiError> {
  return useQuery<Game, ApiError>({
    queryKey: ["games", "detail", gameId],
    queryFn: () => apiFetch<Game>(`/api/v3/game/${gameId}`),
    enabled: gameId !== null,
    staleTime: 30_000,
  });
}

export function useReleasesForGame(
  gameId: number | null,
): UseQueryResult<Release[], ApiError> {
  return useQuery<Release[], ApiError>({
    queryKey: ["games", "releases", gameId],
    queryFn: () => apiFetch<Release[]>(`/api/v3/game/${gameId}/release`),
    enabled: gameId !== null,
    staleTime: 30_000,
  });
}

export function useDumpsForGame(
  gameId: number | null,
): UseQueryResult<Dump[], ApiError> {
  return useQuery<Dump[], ApiError>({
    queryKey: ["games", "dumps", gameId],
    queryFn: () => apiFetch<Dump[]>(`/api/v3/game/${gameId}/dump`),
    enabled: gameId !== null,
    staleTime: 30_000,
  });
}
