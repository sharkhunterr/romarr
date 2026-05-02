/**
 * Queue-mirror TanStack Query hook.
 *
 * Wraps GET /api/v3/queue (spec 013 phase ROUTERS Queue, slice
 * 26). The endpoint returns the canonical PaginationEnvelope
 * of QueueEntryRead records — Sonarr-shape camelCase JSON.
 *
 * Until the WebSocket bridge ships (spec 013 T072), the
 * Activity page polls this hook every 5s for fresh progress
 * data. The WS path is a one-line swap once
 * `queryClient.invalidateQueries(["queue"])` is wired into the
 * `queueUpdated` event handler.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type QueueEntry = components["schemas"]["QueueEntryRead"];

interface QueueEnvelope {
  page: number;
  pageSize: number;
  sortKey: string;
  sortDirection: string;
  totalRecords: number;
  records: QueueEntry[];
}

export interface UseQueueParams {
  page?: number;
  pageSize?: number;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  /**
   * Refetch interval in ms. Defaults to 5000 — short enough
   * that a download's progress feels live without hammering
   * the backend. Set to ``false`` to disable polling.
   */
  refetchInterval?: number | false;
}

export function useQueue(
  params: UseQueueParams = {},
): UseQueryResult<QueueEnvelope, ApiError> {
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined)
    search.set("pageSize", String(params.pageSize));
  if (params.sortKey !== undefined) search.set("sortKey", params.sortKey);
  if (params.sortDirection !== undefined)
    search.set("sortDirection", params.sortDirection);
  const qs = search.toString();

  return useQuery<QueueEnvelope, ApiError>({
    queryKey: ["queue", params],
    queryFn: () =>
      apiFetch<QueueEnvelope>(`/api/v3/queue${qs ? `?${qs}` : ""}`),
    staleTime: 5_000,
    refetchInterval: params.refetchInterval ?? 5_000,
  });
}
