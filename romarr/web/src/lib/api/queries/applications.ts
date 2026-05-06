/**
 * Prowlarr application registration hooks (slice 119).
 *
 * Wraps spec 004 admin surface:
 *   * GET    /api/v3/applications        — list registered
 *     Prowlarr instances (admin only)
 *   * DELETE /api/v3/applications/{id}   — unregister
 *
 * The full registration flow (POST with prowlarr_api_key)
 * lands once the multi-step admin form ships; today's hooks
 * cover the read + revoke surface so the Indexers page can
 * surface the Prowlarr sync status.
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

export type Application = components["schemas"]["ApplicationRead"];
export type ApplicationCreatePayload =
  components["schemas"]["ApplicationCreate"];
export type ApplicationCreateResult =
  components["schemas"]["ApplicationCreateResult"];

const KEY = ["admin", "applications"] as const;

export function useApplications(
  options?: { enabled?: boolean },
): UseQueryResult<Application[], ApiError> {
  return useQuery<Application[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<Application[]>("/api/v3/applications"),
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
}

export function useDeleteApplication(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/applications/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useCreateApplication(): UseMutationResult<
  ApplicationCreateResult,
  ApiError,
  ApplicationCreatePayload
> {
  const qc = useQueryClient();
  return useMutation<
    ApplicationCreateResult,
    ApiError,
    ApplicationCreatePayload
  >({
    mutationFn: (payload) =>
      apiFetch<ApplicationCreateResult>("/api/v3/applications", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ["admin", "indexers"] });
    },
  });
}

/**
 * POST /api/v3/applications/{id}/rotate-token — mint a fresh
 * app_token for an existing registration. Used when the operator
 * lost the original (we only kept the hash) and needs a new one
 * to paste into Prowlarr → Apps → Romarr → Application Token.
 */
export function useRotateApplicationToken(): UseMutationResult<
  ApplicationCreateResult,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<ApplicationCreateResult, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<ApplicationCreateResult>(
        `/api/v3/applications/${id}/rotate-token`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
