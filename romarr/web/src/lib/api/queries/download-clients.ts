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

export type DownloadClient = components["schemas"]["DownloadClientRead"];
export type DownloadClientCreate =
  components["schemas"]["DownloadClientCreate"];
export type DownloadClientType = components["schemas"]["ClientType"];
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

/**
 * Lookup helper — id → DownloadClient. Returns an empty Map until
 * the underlying query resolves. Memoised on the query result so
 * consumers don't rebuild the index on every render. Used by
 * Activity > Queue to surface client names instead of bare ids.
 */
export function useDownloadClientsById(): Map<number, DownloadClient> {
  const clients = useDownloadClients();
  return useMemo(() => {
    const out = new Map<number, DownloadClient>();
    for (const c of clients.data ?? []) {
      out.set(c.id, c);
    }
    return out;
  }, [clients.data]);
}

export function useCreateDownloadClient(): UseMutationResult<
  DownloadClient,
  ApiError,
  DownloadClientCreate
> {
  const qc = useQueryClient();
  return useMutation<DownloadClient, ApiError, DownloadClientCreate>({
    mutationFn: (payload) =>
      apiFetch<DownloadClient>("/api/v3/downloadclient", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
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

/**
 * PUT /api/v3/downloadclient/{id} — narrow toggle subset (slice 123).
 *
 * The DownloadClientUpdate body is broad; this hook only exposes
 * the three operator-level flags (enabled master + the two
 * protocol-specific flags). Full edit (host/port/auth) lands in
 * the multi-step editor slice.
 */
export interface ToggleDownloadClientVariables {
  id: number;
  enabled?: boolean;
  enable_for_torrents?: boolean;
  enable_for_usenet?: boolean;
}

export function useToggleDownloadClient(): UseMutationResult<
  DownloadClient,
  ApiError,
  ToggleDownloadClientVariables
> {
  const qc = useQueryClient();
  return useMutation<
    DownloadClient,
    ApiError,
    ToggleDownloadClientVariables
  >({
    mutationFn: ({ id, ...body }) =>
      apiFetch<DownloadClient>(`/api/v3/downloadclient/${id}`, {
        method: "PUT",
        json: body,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}
