/**
 * Admin user-management hooks (slice 107).
 *
 * Wraps spec 010's admin surface:
 *   * GET    /api/v3/user           — list every user (admin only)
 *   * DELETE /api/v3/user/{id}      — delete (admin only)
 *
 * Read of `/api/v3/user` 403s for non-admin principals; the
 * caller (Settings>General page) gates the section on the
 * principal's role to avoid noisy 403s in dev tools.
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

export type User = components["schemas"]["UserPublic"];

const KEY = ["admin", "users"] as const;

export function useUsers(
  options?: { enabled?: boolean },
): UseQueryResult<User[], ApiError> {
  return useQuery<User[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<User[]>("/api/v3/user"),
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
}

export function useDeleteUser(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/user/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
