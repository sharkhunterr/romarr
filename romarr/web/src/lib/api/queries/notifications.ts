/**
 * Notification CRUD + test TanStack Query hooks (slice 62).
 *
 * Wraps the spec 012 / 013 /api/v3/notification surface:
 *   * GET    /api/v3/notification
 *   * GET    /api/v3/notification/{id}
 *   * DELETE /api/v3/notification/{id}
 *   * POST   /api/v3/notification/{id}/test
 *
 * Backed by Apprise — the SPA never sees the raw URL, only
 * the redacted form (``apprise_url_redacted``). Create + edit
 * forms are deferred to a follow-up slice (NotificationCreate
 * has 7 event toggles + 7 optional Jinja format strings).
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

export type Notification = components["schemas"]["NotificationRead"];
export type NotificationTestResult =
  components["schemas"]["TestNotificationResponse"];

const NOTIFICATIONS_KEY = ["settings", "notifications"] as const;

export function useNotifications(): UseQueryResult<
  Notification[],
  ApiError
> {
  return useQuery<Notification[], ApiError>({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => apiFetch<Notification[]>("/api/v3/notification"),
    staleTime: 30_000,
  });
}

export function useDeleteNotification(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/notification/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}

export function useTestNotification(): UseMutationResult<
  NotificationTestResult,
  ApiError,
  number
> {
  return useMutation<NotificationTestResult, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<NotificationTestResult>(
        `/api/v3/notification/${id}/test`,
        { method: "POST" },
      ),
  });
}
