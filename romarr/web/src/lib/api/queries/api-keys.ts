/**
 * Per-user API key management hooks (slice 106).
 *
 * Wraps spec 010's auth router:
 *   * GET    /api/v3/auth/api-key                — list mine
 *   * POST   /api/v3/auth/api-key                — mint (plaintext
 *     returned ONCE; the response shape is intentionally
 *     different from the public read shape).
 *   * DELETE /api/v3/auth/api-key/{id}           — revoke (idempotent).
 *
 * Plaintext is surfaced once at mint-time and never persisted in
 * the cache — operators must copy it before closing the modal.
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

export type ApiKey = components["schemas"]["ApiKeyPublic"];
export type CreatedApiKey = components["schemas"]["CreatedApiKeyResponse"];

const KEY = ["auth", "api-keys"] as const;

export function useApiKeys(): UseQueryResult<ApiKey[], ApiError> {
  return useQuery<ApiKey[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<ApiKey[]>("/api/v3/auth/api-key"),
    staleTime: 60_000,
  });
}

export interface CreateApiKeyVariables {
  name: string;
  scopes?: string[];
  expiresAt?: string | null;
}

export function useCreateApiKey(): UseMutationResult<
  CreatedApiKey,
  ApiError,
  CreateApiKeyVariables
> {
  const qc = useQueryClient();
  return useMutation<CreatedApiKey, ApiError, CreateApiKeyVariables>({
    mutationFn: ({ name, scopes, expiresAt }) =>
      apiFetch<CreatedApiKey>("/api/v3/auth/api-key", {
        method: "POST",
        json: {
          name,
          scopes: scopes ?? [],
          expires_at: expiresAt ?? null,
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeleteApiKey(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/auth/api-key/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
