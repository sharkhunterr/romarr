/**
 * Library read + delete TanStack Query hooks (slice 92).
 *
 * Wraps spec 009 /api/v3/rom/library:
 *   * GET    /api/v3/rom/library
 *   * GET    /api/v3/rom/library/{id}
 *   * DELETE /api/v3/rom/library/{id}?force=true
 *
 * Create + update flows are deferred to a follow-up slice —
 * LibraryCreate carries many required FKs (the 5 profile
 * bindings + lifecycle policy + paths) that deserve a
 * multi-step form.
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

export type Library = components["schemas"]["LibraryRead"];

const KEY = ["settings", "libraries"] as const;

export function useLibraries(): UseQueryResult<Library[], ApiError> {
  return useQuery<Library[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<Library[]>("/api/v3/rom/library"),
    staleTime: 30_000,
  });
}

export interface DeleteLibraryVariables {
  id: number;
  /**
   * Cascade-detach Releases before deleting (`?force=true`
   * on the server). Default is false; the API returns 409
   * with errorCode `library_has_releases` when this isn't
   * set and Releases reference the library.
   */
  force?: boolean;
}

export function useDeleteLibrary(): UseMutationResult<
  void,
  ApiError,
  DeleteLibraryVariables
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, DeleteLibraryVariables>({
    mutationFn: ({ id, force }) =>
      apiFetch<void>(
        `/api/v3/rom/library/${id}${force ? "?force=true" : ""}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
