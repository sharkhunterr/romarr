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

import { useMemo } from "react";
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
export type IndexerCreate = components["schemas"]["IndexerCreate"];
export type IndexerUpdate = components["schemas"]["IndexerUpdate"];
export type IndexerImplementation = "newznab" | "torznab";
export type IndexerTestResult =
  components["schemas"][
    "romarr__indexers__connectivity__ConnectivityTestResult"
  ];
export type GrabarrWizardRequest =
  components["schemas"]["GrabarrWizardRequest"];
export type GrabarrWizardResponse =
  components["schemas"]["GrabarrWizardResponse"];

const INDEXERS_KEY = ["settings", "indexers"] as const;
const INDEXER_SECRETS_KEY = (id: number) =>
  ["settings", "indexer-secrets", id] as const;

export function useIndexers(): UseQueryResult<Indexer[], ApiError> {
  return useQuery<Indexer[], ApiError>({
    queryKey: INDEXERS_KEY,
    queryFn: () => apiFetch<Indexer[]>("/api/v3/indexer"),
    staleTime: 30_000,
  });
}

/**
 * Fetch a single indexer's DECRYPTED api_key so the edit modal can
 * pre-fill the field. Admin-only backend endpoint, never cached
 * across sessions (gcTime: 0). Skipped for id ≤ 0 (create mode).
 */
export interface IndexerSecrets {
  api_key: string | null;
}

export function useIndexerSecrets(
  indexerId: number | null | undefined,
  enabled: boolean = true,
): UseQueryResult<IndexerSecrets, ApiError> {
  const id = typeof indexerId === "number" ? indexerId : 0;
  return useQuery<IndexerSecrets, ApiError>({
    queryKey: INDEXER_SECRETS_KEY(id),
    queryFn: () =>
      apiFetch<IndexerSecrets>(`/api/v3/indexer/${id}/secrets`),
    enabled: enabled && id > 0,
    staleTime: 0,
    gcTime: 0,
  });
}

/**
 * Lookup helper — id → Indexer. Returns an empty Map until the
 * underlying query resolves. Memoised on the query result so
 * consumers don't rebuild the index on every render. Used by
 * the manual-search modal to surface indexer names instead of
 * bare ids on each candidate row.
 */
export function useIndexersById(): Map<number, Indexer> {
  const indexers = useIndexers();
  return useMemo(() => {
    const out = new Map<number, Indexer>();
    for (const i of indexers.data ?? []) {
      out.set(i.id, i);
    }
    return out;
  }, [indexers.data]);
}

export function useCreateIndexer(): UseMutationResult<
  Indexer,
  ApiError,
  IndexerCreate
> {
  const qc = useQueryClient();
  return useMutation<Indexer, ApiError, IndexerCreate>({
    mutationFn: (payload) =>
      apiFetch<Indexer>("/api/v3/indexer", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
    },
  });
}

/**
 * Slice 428 / R3b — atomic "Add Grabarr" wizard.
 *
 * Hits POST /api/v3/indexer/grabarr, which probes /health on the
 * operator's Grabarr deploy and then creates the linked
 * download_client + indexer pair under a single transaction.
 * Invalidates both the indexer list AND the download-client list
 * so the Settings → Download Clients view picks the new row up
 * too without a manual refresh.
 */
export function useCreateGrabarrIntegration(): UseMutationResult<
  GrabarrWizardResponse,
  ApiError,
  GrabarrWizardRequest
> {
  const qc = useQueryClient();
  return useMutation<GrabarrWizardResponse, ApiError, GrabarrWizardRequest>({
    mutationFn: (payload) =>
      apiFetch<GrabarrWizardResponse>("/api/v3/indexer/grabarr", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
      // Reuse the same key the download-client queries use.
      void qc.invalidateQueries({ queryKey: ["settings", "downloadClients"] });
    },
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
  // Slice 431 — the backend now persists ``last_health_*`` on the
  // row after every manual test. Invalidate the list query so the
  // row's health dot + badge re-render with the fresh outcome
  // instead of staying stuck on "untested".
  const qc = useQueryClient();
  return useMutation<IndexerTestResult, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<IndexerTestResult>(`/api/v3/indexer/${id}/test`, {
        method: "POST",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
    },
  });
}

/**
 * POST /api/v3/indexer/test — probe an unsaved (URL, api_key)
 * pair. Lets the operator validate connectivity from inside the
 * Create / Edit modal without having to save first.
 */
export interface IndexerProbePayload {
  implementation: IndexerImplementation;
  url: string;
  api_key: string | null;
}

export function useProbeIndexer(): UseMutationResult<
  IndexerTestResult,
  ApiError,
  IndexerProbePayload
> {
  return useMutation<IndexerTestResult, ApiError, IndexerProbePayload>({
    mutationFn: (payload) =>
      apiFetch<IndexerTestResult>("/api/v3/indexer/test", {
        method: "POST",
        json: payload,
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
  // Slice 432 — master kill-switch. When false the indexer is
  // hidden from every search round + RSS poll + grab dispatch
  // regardless of the per-capability flags below.
  enabled?: boolean;
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

/**
 * PUT /api/v3/indexer/{id} — full edit. Pass any subset of
 * IndexerUpdate fields; the backend re-encrypts ``api_key`` only
 * when present in the body, so leaving it omitted preserves the
 * existing key (operator can edit name/url without re-typing).
 */
export interface UpdateIndexerVariables {
  id: number;
  payload: IndexerUpdate;
}

export function useUpdateIndexer(): UseMutationResult<
  Indexer,
  ApiError,
  UpdateIndexerVariables
> {
  const qc = useQueryClient();
  return useMutation<Indexer, ApiError, UpdateIndexerVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<Indexer>(`/api/v3/indexer/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: INDEXERS_KEY });
    },
  });
}
