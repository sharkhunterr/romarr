/**
 * Custom Format query / mutation hooks (slice 64).
 *
 * Wraps spec 007 / 013 /api/v3/customformat:
 *   * GET    /api/v3/customformat          (list)
 *   * GET    /api/v3/customformat/{id}     (read)
 *   * DELETE /api/v3/customformat/{id}     (admin)
 *
 * Create + update flows are deferred — the visual condition
 * builder (T097) is a meaty UX slice on its own. The MVP page
 * surfaces the read path so operators can audit the
 * factory-default catalogue and what's been customized.
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

export type CustomFormat = components["schemas"]["CustomFormatRead"];

const CUSTOM_FORMATS_KEY = ["settings", "custom-formats"] as const;

export function useCustomFormats(): UseQueryResult<CustomFormat[], ApiError> {
  return useQuery<CustomFormat[], ApiError>({
    queryKey: CUSTOM_FORMATS_KEY,
    queryFn: () => apiFetch<CustomFormat[]>("/api/v3/customformat"),
    staleTime: 30_000,
  });
}

export function useDeleteCustomFormat(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/customformat/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CUSTOM_FORMATS_KEY });
    },
  });
}
