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

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type QueueEntry = components["schemas"]["QueueEntryRead"];

export type QueueState =
  | "queued"
  | "downloading"
  | "paused"
  | "completed"
  | "stuck"
  | "failed"
  | "pending_retry";

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
  /** Filter to one Game's queue (joined via Release). */
  gameId?: number;
  /** Filter to one Release's queue. */
  releaseId?: number;
  /** Filter to one queue state. */
  state?: QueueState;
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
  if (params.gameId !== undefined) search.set("gameId", String(params.gameId));
  if (params.releaseId !== undefined)
    search.set("releaseId", String(params.releaseId));
  if (params.state !== undefined) search.set("state", params.state);
  const qs = search.toString();

  return useQuery<QueueEnvelope, ApiError>({
    queryKey: ["queue", params],
    queryFn: () =>
      apiFetch<QueueEnvelope>(`/api/v3/queue${qs ? `?${qs}` : ""}`),
    staleTime: 5_000,
    refetchInterval: params.refetchInterval ?? 5_000,
  });
}


/**
 * Drop a queue entry — delegates to spec 013 slice 234's
 * DELETE ``/api/v3/queue/{id}``. ``removeFromClient`` defaults
 * to ``false`` (delete only the Romarr-side mirror); set to
 * ``true`` to also call ``DownloadClient.remove(delete_files=True)``
 * via the spec 005 factory so the on-disk download is dropped.
 *
 * On success the [["queue"]] cache is invalidated so the
 * Activity page re-renders without the dropped entry.
 */
export interface DeleteQueueEntryVariables {
  id: number;
  removeFromClient?: boolean;
}

export function useDeleteQueueEntry(): UseMutationResult<
  void,
  ApiError,
  DeleteQueueEntryVariables
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, DeleteQueueEntryVariables>({
    mutationFn: async ({ id, removeFromClient }) => {
      const qs =
        removeFromClient === true ? "?removeFromClient=true" : "";
      await apiFetch<void>(`/api/v3/queue/${id}${qs}`, {
        method: "DELETE",
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}
