/**
 * Metadata provider query / mutation hooks (slice 63).
 *
 * Wraps spec 002 / 013 /api/v3/metadata/provider:
 *   * GET    /api/v3/metadata/provider  (list)
 *   * PUT    /api/v3/metadata/provider/{name}  (enable / priority / RL)
 *   * POST   /api/v3/metadata/provider/{name}/test  (live probe)
 *
 * Field-priority editing (per-field provider order) lives at
 * /api/v3/metadata/field-priority and lands in its own slice
 * once the drag-and-drop UI is wired.
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

export type MetadataProvider = components["schemas"]["ProviderConfigRead"];
export type MetadataProviderUpdate =
  components["schemas"]["ProviderConfigUpdate"];
export type MetadataProviderTestResult =
  components["schemas"]["ProviderTestResponse"];

const PROVIDERS_KEY = ["settings", "metadata-providers"] as const;

export function useMetadataProviders(): UseQueryResult<
  MetadataProvider[],
  ApiError
> {
  return useQuery<MetadataProvider[], ApiError>({
    queryKey: PROVIDERS_KEY,
    queryFn: () => apiFetch<MetadataProvider[]>("/api/v3/metadata/provider"),
    staleTime: 30_000,
  });
}

export interface UpdateMetadataProviderVariables {
  providerName: string;
  payload: MetadataProviderUpdate;
}

export function useUpdateMetadataProvider(): UseMutationResult<
  MetadataProvider,
  ApiError,
  UpdateMetadataProviderVariables
> {
  const qc = useQueryClient();
  return useMutation<
    MetadataProvider,
    ApiError,
    UpdateMetadataProviderVariables
  >({
    mutationFn: ({ providerName, payload }) =>
      apiFetch<MetadataProvider>(
        `/api/v3/metadata/provider/${providerName}`,
        { method: "PUT", json: payload },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}

export function useTestMetadataProvider(): UseMutationResult<
  MetadataProviderTestResult,
  ApiError,
  string
> {
  return useMutation<MetadataProviderTestResult, ApiError, string>({
    mutationFn: (providerName) =>
      apiFetch<MetadataProviderTestResult>(
        `/api/v3/metadata/provider/${providerName}/test`,
        { method: "POST" },
      ),
  });
}
