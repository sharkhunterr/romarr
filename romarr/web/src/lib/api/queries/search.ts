/**
 * Manual-search + grab mutations (slice 102).
 *
 * Wraps the spec 007 admin surface:
 *   * POST /api/v3/rom/search/manual — runs a one-shot manual
 *     search round and returns every candidate (winners +
 *     rejections) so the operator can pick. Admin only.
 *   * POST /api/v3/rom/release/grab  — dispatches one chosen
 *     candidate to the routed download client. Optional
 *     ?force=true overrides the blocklist gate.
 *
 * Both mutations are short-lived (search round + grab); we
 * don't cache results — each search is a fresh round against
 * the live indexers.
 */

import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type SearchRoundReport = components["schemas"]["SearchRoundReport"];
export type Candidate = components["schemas"]["Candidate"];

export interface ManualSearchVariables {
  query: string;
  /** Restrict to a subset of indexers; default = every enabled. */
  indexerIds?: number[];
  /** Restrict to one platform's queries. */
  platformId?: number;
  /** Drop auto-reject candidates from the response. */
  strict?: boolean;
  /** Scope the round to a specific game card. When set, the
   * backend writes ONE search_history row for this game instead
   * of fanning out across every fuzzy-matched library game —
   * so the game's History tab doesn't fill up with phantom
   * searches the operator never initiated. */
  gameId?: number;
}

export function useManualSearch(): UseMutationResult<
  SearchRoundReport,
  ApiError,
  ManualSearchVariables
> {
  return useMutation<SearchRoundReport, ApiError, ManualSearchVariables>({
    mutationFn: ({ query, indexerIds, platformId, strict, gameId }) =>
      apiFetch<SearchRoundReport>("/api/v3/rom/search/manual", {
        method: "POST",
        json: {
          query,
          indexer_ids: indexerIds,
          platform_id: platformId,
          strict: strict ?? false,
          game_id: gameId,
        },
      }),
  });
}

export interface ManualGrabVariables {
  indexerId: number;
  indexerGuid: string;
  downloadUrl: string;
  title: string;
  /** The game the modal opened for (game-level manual search).
   * Filled into ``search_history.game_id`` so the per-game
   * History tab surfaces this manual grab. */
  gameId?: number;
  releaseId?: number;
  /** Override the blocklist gate (FR-022). */
  force?: boolean;
}

export function useManualGrab(): UseMutationResult<
  Record<string, unknown>,
  ApiError,
  ManualGrabVariables
> {
  const qc = useQueryClient();
  return useMutation<Record<string, unknown>, ApiError, ManualGrabVariables>({
    mutationFn: ({ force, releaseId, gameId, ...body }) =>
      apiFetch<Record<string, unknown>>(
        `/api/v3/rom/release/grab${force ? "?force=true" : ""}`,
        {
          method: "POST",
          json: {
            indexer_id: body.indexerId,
            indexer_guid: body.indexerGuid,
            download_url: body.downloadUrl,
            title: body.title,
            game_id: gameId,
            release_id: releaseId,
          },
        },
      ),
    onSuccess: () => {
      // Activity / Queue + History will catch the new entry.
      void qc.invalidateQueries({ queryKey: ["queue"] });
      void qc.invalidateQueries({ queryKey: ["system", "history"] });
    },
  });
}
