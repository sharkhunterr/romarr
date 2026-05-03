/**
 * Metadata-lookup hooks (slices 144 + 145).
 *
 * Wraps:
 *   - `GET  /api/v3/game/lookup` — admin-only aggregated search
 *     across every enabled metadata provider. Returns a
 *     confidence-ranked list of provider candidates the operator
 *     can pick from on the AddNew page.
 *   - `POST /api/v3/game/lookup/add` — instantiates a Game from
 *     a chosen lookup candidate; the metadata aggregator
 *     enriches the rest of the fields asynchronously via the
 *     ``needs_metadata_refresh`` flag.
 *
 * The query hook is gated on `q.length > 0` so an empty input
 * doesn't fire a search round on every keystroke.
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

export type GameLookupRow = components["schemas"]["GameLookupRow"];
export type LookupAddRequest = components["schemas"]["LookupAddRequest"];
export type GameRead = components["schemas"]["GameRead"];

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

/**
 * Add a Game to the Library from a lookup candidate.
 *
 * On success we invalidate the games query keys so Library /
 * Wanted reflect the new row immediately. The mutation result
 * carries the full GameRead — callers typically navigate to
 * `/game/{id}` afterwards.
 */
export function useAddGameFromLookup(): UseMutationResult<
  GameRead,
  ApiError,
  LookupAddRequest
> {
  const qc = useQueryClient();
  return useMutation<GameRead, ApiError, LookupAddRequest>({
    mutationFn: (payload) =>
      apiFetch<GameRead>("/api/v3/game/lookup/add", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      // The new row affects every game-scoped surface.
      void qc.invalidateQueries({ queryKey: ["games"] });
      void qc.invalidateQueries({ queryKey: ["wanted"] });
    },
  });
}
