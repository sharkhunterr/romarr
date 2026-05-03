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
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type Game = components["schemas"]["GameRead"];
export type Release = components["schemas"]["ReleaseRead"];
export type Dump = components["schemas"]["DumpRead"];
export type RefreshMetadataResponse =
  components["schemas"]["RefreshMetadataResponse"];

export type GameSortKey = "title" | "added_at" | "release_date" | "rating";
export type SortDirection = "asc" | "desc";

export interface ListGamesParams {
  q?: string;
  platformId?: number;
  /** Filter on the `monitored` flag. */
  monitored?: boolean;
  sort?: GameSortKey;
  direction?: SortDirection;
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
  if (params.monitored !== undefined)
    search.set("monitored", String(params.monitored));
  if (params.sort !== undefined) search.set("sort", params.sort);
  if (params.direction !== undefined)
    search.set("direction", params.direction);
  if (params.limit !== undefined) {
    search.set("limit", String(params.limit));
  }
  const qs = search.toString();
  const url = qs ? `/api/v3/game?${qs}` : "/api/v3/game";

  return useQuery<Game[], ApiError>({
    queryKey: [
      "games",
      "list",
      params.q ?? "",
      params.platformId ?? null,
      params.monitored ?? null,
      params.sort ?? null,
      params.direction ?? null,
      params.limit ?? null,
    ],
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

export interface ToggleMonitorVariables {
  gameId: number;
  monitored: boolean;
}

export interface RefreshMetadataVariables {
  gameId: number;
  /**
   * Bypass the cache TTL on metadata providers. Defaults to
   * `false` (the spec 002 cache decides per-provider).
   */
  force?: boolean;
}

/**
 * POST /api/v3/game/{id}/refresh-metadata — re-aggregate metadata
 * from the enabled providers. Locked fields (FR-008) are
 * preserved. The response carries which fields actually changed
 * and which were skipped because the operator pinned them; the
 * detail query is invalidated so cover + summary re-render.
 */
export function useRefreshGameMetadata(): UseMutationResult<
  RefreshMetadataResponse,
  ApiError,
  RefreshMetadataVariables
> {
  const qc = useQueryClient();
  return useMutation<
    RefreshMetadataResponse,
    ApiError,
    RefreshMetadataVariables
  >({
    mutationFn: ({ gameId, force }) =>
      apiFetch<RefreshMetadataResponse>(
        `/api/v3/game/${gameId}/refresh-metadata${force ? "?force=true" : ""}`,
        { method: "POST" },
      ),
    onSuccess: (result) => {
      void qc.invalidateQueries({
        queryKey: ["games", "detail", result.game_id],
      });
      void qc.invalidateQueries({ queryKey: ["games", "list"] });
    },
  });
}

export interface ToggleReleaseMonitorVariables {
  releaseId: number;
  /** The owning game — used to invalidate just that game's release cache. */
  gameId: number;
  monitored: boolean;
}

/**
 * PATCH /api/v3/rom/release/{id} — toggle a release's `monitored`
 * flag. On success the per-game releases cache is invalidated.
 */
export function useToggleReleaseMonitor(): UseMutationResult<
  Release,
  ApiError,
  ToggleReleaseMonitorVariables
> {
  const qc = useQueryClient();
  return useMutation<Release, ApiError, ToggleReleaseMonitorVariables>({
    mutationFn: ({ releaseId, monitored }) =>
      apiFetch<Release>(`/api/v3/rom/release/${releaseId}`, {
        method: "PATCH",
        json: { monitored },
      }),
    onSuccess: (_release, variables) => {
      void qc.invalidateQueries({
        queryKey: ["games", "releases", variables.gameId],
      });
    },
  });
}

/**
 * PATCH /api/v3/game/{id} — toggle a game's `monitored` flag.
 *
 * On success the canonical detail + list query keys are
 * invalidated so the GameDetail header and the Library card
 * pick up the new state without a manual refresh.
 */
export function useToggleGameMonitor(): UseMutationResult<
  Game,
  ApiError,
  ToggleMonitorVariables
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, ToggleMonitorVariables>({
    mutationFn: ({ gameId, monitored }) =>
      apiFetch<Game>(`/api/v3/game/${gameId}`, {
        method: "PATCH",
        json: { monitored },
      }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
      void qc.invalidateQueries({ queryKey: ["games", "list"] });
    },
  });
}
