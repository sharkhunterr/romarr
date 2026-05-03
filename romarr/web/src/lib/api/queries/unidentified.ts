/**
 * Unidentified-dump TanStack Query hooks (slice 87).
 *
 * Wraps the spec 008 /api/v3/rom/unidentified surface
 * (slice 84 wired the match endpoint):
 *   * GET    /api/v3/rom/unidentified
 *   * POST   /api/v3/rom/unidentified/{id}/match
 *   * DELETE /api/v3/rom/unidentified/{id}
 *
 * The match mutation invalidates the list query on success so
 * the row drops off the operator's triage view immediately.
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

export type UnidentifiedDump = components["schemas"]["UnidentifiedDumpRead"];
export type ImportHistory = components["schemas"]["ImportHistoryRead"];
export type ManualMatchRequest = components["schemas"]["ManualMatchRequest"];

const UNIDENTIFIED_KEY = ["unidentified"] as const;

export function useUnidentified(): UseQueryResult<UnidentifiedDump[], ApiError> {
  return useQuery<UnidentifiedDump[], ApiError>({
    queryKey: UNIDENTIFIED_KEY,
    queryFn: () => apiFetch<UnidentifiedDump[]>("/api/v3/rom/unidentified"),
    staleTime: 30_000,
  });
}

export function useDeleteUnidentified(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom/unidentified/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: UNIDENTIFIED_KEY });
    },
  });
}

export interface MatchVariables {
  id: number;
  payload: ManualMatchRequest;
}

export function useMatchUnidentified(): UseMutationResult<
  ImportHistory,
  ApiError,
  MatchVariables
> {
  const qc = useQueryClient();
  return useMutation<ImportHistory, ApiError, MatchVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<ImportHistory>(
        `/api/v3/rom/unidentified/${id}/match`,
        { method: "POST", json: payload },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: UNIDENTIFIED_KEY });
      // History list (Activity / Dashboard) gains a new row too.
      void qc.invalidateQueries({ queryKey: ["history"] });
    },
  });
}
