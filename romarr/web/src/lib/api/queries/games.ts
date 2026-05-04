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
  tagId?: number;
  /**
   * Restrict to games that have at least one Release bound to
   * this Library id (slice 166).
   */
  libraryId?: number;
  /** Filter on the `monitored` flag. */
  monitored?: boolean;
  /** Restrict to games whose ``Game.genres`` contains this value. */
  genre?: string;
  /** Restrict to games whose ``Game.regions`` contains this code. */
  region?: string;
  /** Restrict to games released in this calendar year. */
  year?: number;
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
  if (params.tagId !== undefined) {
    search.set("tag_id", String(params.tagId));
  }
  if (params.libraryId !== undefined) {
    search.set("library_id", String(params.libraryId));
  }
  if (params.monitored !== undefined)
    search.set("monitored", String(params.monitored));
  if (params.genre !== undefined && params.genre.trim()) {
    search.set("genre", params.genre.trim());
  }
  if (params.region !== undefined && params.region.trim()) {
    search.set("region", params.region.trim());
  }
  if (params.year !== undefined) {
    search.set("year", String(params.year));
  }
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

export type BulkReleaseMonitorResponse =
  components["schemas"]["BulkReleaseMonitorResponse"];

export interface BulkReleaseMonitorVariables {
  releaseIds: number[];
  monitored: boolean;
}

/**
 * POST /api/v3/rom/release/bulk-monitor — flip the monitored
 * flag on a batch of Releases (slice 152). Capped at 500 ids
 * per call. Powers the Wanted page bulk-select toolbar.
 */
export function useBulkMonitorReleases(): UseMutationResult<
  BulkReleaseMonitorResponse,
  ApiError,
  BulkReleaseMonitorVariables
> {
  const qc = useQueryClient();
  return useMutation<
    BulkReleaseMonitorResponse,
    ApiError,
    BulkReleaseMonitorVariables
  >({
    mutationFn: ({ releaseIds, monitored }) =>
      apiFetch<BulkReleaseMonitorResponse>(
        "/api/v3/rom/release/bulk-monitor",
        {
          method: "POST",
          json: { releaseIds, monitored },
        },
      ),
    onSuccess: () => {
      // Wanted is the consumer; invalidate any release-scoped
      // game caches so per-game Releases tabs repaint too.
      void qc.invalidateQueries({ queryKey: ["wanted"] });
      void qc.invalidateQueries({ queryKey: ["games", "releases"] });
    },
  });
}

export type BulkReleaseDeleteResponse =
  components["schemas"]["BulkReleaseDeleteResponse"];

export interface BulkReleaseDeleteVariables {
  releaseIds: number[];
}

/**
 * POST /api/v3/rom/release/bulk-delete — destroy a batch of
 * Releases (slice 155). Cascades to Dump rows; never touches
 * ROM files on disk.
 */
export function useBulkDeleteReleases(): UseMutationResult<
  BulkReleaseDeleteResponse,
  ApiError,
  BulkReleaseDeleteVariables
> {
  const qc = useQueryClient();
  return useMutation<
    BulkReleaseDeleteResponse,
    ApiError,
    BulkReleaseDeleteVariables
  >({
    mutationFn: ({ releaseIds }) =>
      apiFetch<BulkReleaseDeleteResponse>(
        "/api/v3/rom/release/bulk-delete",
        {
          method: "POST",
          json: { releaseIds },
        },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["wanted"] });
      void qc.invalidateQueries({ queryKey: ["games", "releases"] });
      void qc.invalidateQueries({ queryKey: ["games"] });
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

export type ProviderField = components["schemas"]["ProviderField"];

export interface ToggleFieldLockVariables {
  gameId: number;
  field: ProviderField;
  locked: boolean;
}

/**
 * PATCH /api/v3/game/{id}/locked-fields — toggle one field's
 * lock state (slice 146 — anti-RomM-#1770).
 *
 * Locked fields are skipped by the metadata aggregator on every
 * refresh, so the operator's manual edits survive forever. The
 * canonical detail key is invalidated on success so the
 * Overview tab repaints with the new lock badge immediately.
 */
export function useToggleFieldLock(): UseMutationResult<
  Game,
  ApiError,
  ToggleFieldLockVariables
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, ToggleFieldLockVariables>({
    mutationFn: ({ gameId, field, locked }) =>
      apiFetch<Game>(`/api/v3/game/${gameId}/locked-fields`, {
        method: "PATCH",
        json: { field, locked },
      }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
    },
  });
}

/** Text fields the operator can edit inline on Overview. */
export type EditableTextField =
  | "title"
  | "summary"
  | "developer"
  | "publisher"
  | "age_rating";

export type BulkMonitorResponse =
  components["schemas"]["BulkMonitorResponse"];

export interface BulkMonitorVariables {
  gameIds: number[];
  monitored: boolean;
}

/**
 * POST /api/v3/game/bulk-monitor — flip the monitored flag on
 * a batch of Games (slice 151). Capped at 500 ids per call;
 * the Library page shards larger selections client-side.
 */
export function useBulkMonitorGames(): UseMutationResult<
  BulkMonitorResponse,
  ApiError,
  BulkMonitorVariables
> {
  const qc = useQueryClient();
  return useMutation<BulkMonitorResponse, ApiError, BulkMonitorVariables>({
    mutationFn: ({ gameIds, monitored }) =>
      apiFetch<BulkMonitorResponse>("/api/v3/game/bulk-monitor", {
        method: "POST",
        json: { gameIds, monitored },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["games"] });
      void qc.invalidateQueries({ queryKey: ["wanted"] });
    },
  });
}

export type BulkDeleteResponse =
  components["schemas"]["BulkDeleteResponse"];

export interface BulkDeleteVariables {
  gameIds: number[];
}

export type BulkTagResponse =
  components["schemas"]["BulkTagResponse"];

export interface BulkTagVariables {
  gameIds: number[];
  tagIds: number[];
  action: "add" | "remove";
}

/**
 * POST /api/v3/game/bulk-tag — apply or strip a set of tags
 * across a batch of Games (slice 154). The Library bulk
 * toolbar drives this; the per-row tag list is kept sorted
 * and deduped server-side.
 */
export function useBulkTagGames(): UseMutationResult<
  BulkTagResponse,
  ApiError,
  BulkTagVariables
> {
  const qc = useQueryClient();
  return useMutation<BulkTagResponse, ApiError, BulkTagVariables>({
    mutationFn: ({ gameIds, tagIds, action }) =>
      apiFetch<BulkTagResponse>("/api/v3/game/bulk-tag", {
        method: "POST",
        json: { gameIds, tagIds, action },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["games"] });
    },
  });
}

/**
 * POST /api/v3/game/bulk-delete — destroy a batch of Games
 * (slice 153). Cascades through Releases / Dumps via FK
 * cascade; on-disk ROM files are NOT touched (constitutional
 * rule: only per-library lifecycle policies remove files).
 */
export function useBulkDeleteGames(): UseMutationResult<
  BulkDeleteResponse,
  ApiError,
  BulkDeleteVariables
> {
  const qc = useQueryClient();
  return useMutation<BulkDeleteResponse, ApiError, BulkDeleteVariables>({
    mutationFn: ({ gameIds }) =>
      apiFetch<BulkDeleteResponse>("/api/v3/game/bulk-delete", {
        method: "POST",
        json: { gameIds },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["games"] });
      void qc.invalidateQueries({ queryKey: ["wanted"] });
    },
  });
}

export interface SetCoverVariables {
  gameId: number;
  url: string;
  autoLock?: boolean;
}

/**
 * PUT /api/v3/cover/{gameId} — operator URL-paste cover
 * override (slice 160). Auto-locks the cover field by default
 * so the next aggregator refresh respects the operator's pick.
 */
export function useSetGameCover(): UseMutationResult<
  Game,
  ApiError,
  SetCoverVariables
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, SetCoverVariables>({
    mutationFn: ({ gameId, url, autoLock }) =>
      apiFetch<Game>(`/api/v3/cover/${gameId}`, {
        method: "PUT",
        json: { url, auto_lock: autoLock ?? true },
      }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
      void qc.invalidateQueries({ queryKey: ["games", "list"] });
    },
  });
}

/**
 * DELETE /api/v3/cover/{gameId} — clear the cover. The
 * aggregator will refetch on the next refresh unless the
 * cover field is locked.
 */
export function useDeleteGameCover(): UseMutationResult<
  Game,
  ApiError,
  { gameId: number }
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, { gameId: number }>({
    mutationFn: ({ gameId }) =>
      apiFetch<Game>(`/api/v3/cover/${gameId}`, { method: "DELETE" }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
      void qc.invalidateQueries({ queryKey: ["games", "list"] });
    },
  });
}

export interface SetGameNotesVariables {
  gameId: number;
  notes: string | null;
}

/**
 * PUT /api/v3/game/{id}/notes — replace operator-owned notes
 * (slice 149). Notes never flow through the metadata aggregator,
 * so the surface stays minimal and untouched by lock state.
 */
export function useSetGameNotes(): UseMutationResult<
  Game,
  ApiError,
  SetGameNotesVariables
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, SetGameNotesVariables>({
    mutationFn: ({ gameId, notes }) =>
      apiFetch<Game>(`/api/v3/game/${gameId}/notes`, {
        method: "PUT",
        json: { notes },
      }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
    },
  });
}

export interface EditFieldVariables {
  gameId: number;
  field: EditableTextField;
  value: string | null;
  autoLock?: boolean;
}

/**
 * PATCH /api/v3/game/{id}/field — manually edit one text
 * metadata field (slice 147 — edit-in-place complement to the
 * slice-146 lock surface).
 *
 * Auto-locks the field by default so the next aggregator
 * refresh respects the operator's edit.
 */
export function useEditGameField(): UseMutationResult<
  Game,
  ApiError,
  EditFieldVariables
> {
  const qc = useQueryClient();
  return useMutation<Game, ApiError, EditFieldVariables>({
    mutationFn: ({ gameId, field, value, autoLock }) =>
      apiFetch<Game>(`/api/v3/game/${gameId}/field`, {
        method: "PATCH",
        json: {
          field,
          value,
          auto_lock: autoLock ?? true,
        },
      }),
    onSuccess: (game) => {
      void qc.invalidateQueries({ queryKey: ["games", "detail", game.id] });
      void qc.invalidateQueries({ queryKey: ["games", "list"] });
    },
  });
}
