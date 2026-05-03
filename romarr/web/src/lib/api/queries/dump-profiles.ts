/**
 * Dump-profile read + delete hooks (slice 91).
 *
 * Same pattern as region/language/quality. Read + delete.
 * Full editor (allowed_dump_status multi-select + the four
 * allow_* toggles + prefer_revision picker) lands in a
 * follow-up slice.
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

export type DumpProfile = components["schemas"]["DumpProfileRead"];

const KEY = ["settings", "dump-profiles"] as const;

export function useDumpProfiles(): UseQueryResult<DumpProfile[], ApiError> {
  return useQuery<DumpProfile[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<DumpProfile[]>("/api/v3/rom/dumpprofile"),
    staleTime: 30_000,
  });
}

export function useDeleteDumpProfile(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom/dumpprofile/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
