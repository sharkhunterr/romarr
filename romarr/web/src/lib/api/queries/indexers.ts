/**
 * Indexer CRUD + connectivity-test TanStack Query hooks.
 *
 * Wraps the spec 005 / 013 /api/v3/indexer surface:
 *   * GET    /api/v3/indexer
 *   * GET    /api/v3/indexer/{id}
 *   * DELETE /api/v3/indexer/{id}
 *   * POST   /api/v3/indexer/{id}/test
 *
 * Create / update flows live in their own forms — too many
 * required fields to bake into a single mutation today.
 * Consumers wiring those forms should call apiFetch directly
 * with the IndexerCreate / IndexerUpdate schemas.
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

export type Indexer = components["schemas"]["IndexerRead"];
export type IndexerTestResult =
  components["schemas"][
    "romarr__indexers__connectivity__ConnectivityTestResult"
  ];

const INDEXERS_KEY = ["settings", "indexers"] as const;

export function useIndexers(): UseQueryResult<Indexer[], ApiError> {
  return useQuery<Indexer[], ApiError>({
    queryKey: INDEXERS_KEY,
    queryFn: () => apiFetch<Indexer[]>("/api/v3/indexer"),
    staleTime: 30_000,
  });
}

export function useDeleteIndexer(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/indexer/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
    },
  });
}

export function useTestIndexer(): UseMutationResult<
  IndexerTestResult,
  ApiError,
  number
> {
  return useMutation<IndexerTestResult, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<IndexerTestResult>(`/api/v3/indexer/${id}/test`, {
        method: "POST",
      }),
  });
}

/**
 * PUT /api/v3/indexer/{id} — narrow toggle subset (slice 122).
 *
 * The IndexerUpdate body is broad; this hook only exposes the
 * three search-mode toggles operators flip from the audit list.
 * The full edit form (URL / categories / api_key rotation /
 * priority) lands when the multi-step indexer-editor slice
 * ships.
 */
export interface ToggleIndexerVariables {
  id: number;
  enable_rss?: boolean;
  enable_automatic_search?: boolean;
  enable_interactive_search?: boolean;
}

export function useToggleIndexer(): UseMutationResult<
  Indexer,
  ApiError,
  ToggleIndexerVariables
> {
  const qc = useQueryClient();
  return useMutation<Indexer, ApiError, ToggleIndexerVariables>({
    mutationFn: ({ id, ...body }) =>
      apiFetch<Indexer>(`/api/v3/indexer/${id}`, {
        method: "PUT",
        json: body,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
    },
  });
}
