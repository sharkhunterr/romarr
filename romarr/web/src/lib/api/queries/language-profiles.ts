/**
 * Language-profile read + delete hooks (slice 90).
 *
 * Same shape as region-profiles.ts; full editor (required +
 * preferred ordered lists) lands in a follow-up slice.
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

export type LanguageProfile = components["schemas"]["LanguageProfileRead"];

const KEY = ["settings", "language-profiles"] as const;

export function useLanguageProfiles(): UseQueryResult<
  LanguageProfile[],
  ApiError
> {
  return useQuery<LanguageProfile[], ApiError>({
    queryKey: KEY,
    queryFn: () =>
      apiFetch<LanguageProfile[]>("/api/v3/rom/languageprofile"),
    staleTime: 30_000,
  });
}

export function useDeleteLanguageProfile(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom/languageprofile/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
