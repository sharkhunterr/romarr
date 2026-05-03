/**
 * Naming-profile read + delete hooks (slice 91).
 *
 * Same shape as the other profile hooks. Live preview against
 * /api/v3/rom/namingprofile/preview lands in a follow-up
 * slice when the editor is wired.
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

export type NamingProfile = components["schemas"]["NamingProfileRead"];

const KEY = ["settings", "naming-profiles"] as const;

export function useNamingProfiles(): UseQueryResult<NamingProfile[], ApiError> {
  return useQuery<NamingProfile[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<NamingProfile[]>("/api/v3/rom/namingprofile"),
    staleTime: 30_000,
  });
}

export function useDeleteNamingProfile(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom/namingprofile/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
