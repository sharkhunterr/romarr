/**
 * Download client CRUD + connectivity-test TanStack Query hooks.
 *
 * Wraps the spec 006 / 013 /api/v3/downloadclient surface:
 *   * GET    /api/v3/downloadclient
 *   * GET    /api/v3/downloadclient/{id}
 *   * DELETE /api/v3/downloadclient/{id}
 *   * POST   /api/v3/downloadclient/{id}/test
 *
 * Create / update flows live in their own forms — too many
 * required fields to bake into a single mutation today.
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

export type DownloadClient = components["schemas"]["DownloadClientRead"];
export type DownloadClientTestResult =
  components["schemas"][
    "romarr__downloaders__types__ConnectivityTestResult"
  ];

const CLIENTS_KEY = ["settings", "download-clients"] as const;

export function useDownloadClients(): UseQueryResult<
  DownloadClient[],
  ApiError
> {
  return useQuery<DownloadClient[], ApiError>({
    queryKey: CLIENTS_KEY,
    queryFn: () => apiFetch<DownloadClient[]>("/api/v3/downloadclient"),
    staleTime: 30_000,
  });
}

export function useDeleteDownloadClient(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/downloadclient/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}

export function useTestDownloadClient(): UseMutationResult<
  DownloadClientTestResult,
  ApiError,
  number
> {
  return useMutation<DownloadClientTestResult, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<DownloadClientTestResult>(
        `/api/v3/downloadclient/${id}/test`,
        { method: "POST" },
      ),
  });
}
