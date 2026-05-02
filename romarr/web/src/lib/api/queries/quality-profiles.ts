/**
 * Quality Profile query / mutation hooks (slice 65).
 *
 * Wraps spec 007 / 013 /api/v3/qualityprofile:
 *   * GET    /api/v3/qualityprofile
 *   * GET    /api/v3/qualityprofile/{id}
 *   * DELETE /api/v3/qualityprofile/{id}
 *
 * Create + update flows ship in their own form slices —
 * a Quality Profile carries an ordered allowed_formats list
 * + preferred / upgrade-until format pickers + DAT toggle +
 * archive policy, which is enough to deserve a dedicated form.
 * The MVP audit / list / delete pattern unblocks operators
 * inspecting the factory-default catalogue today.
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

export type QualityProfile = components["schemas"]["QualityProfileRead"];

const QUALITY_PROFILES_KEY = ["settings", "quality-profiles"] as const;

export function useQualityProfiles(): UseQueryResult<
  QualityProfile[],
  ApiError
> {
  return useQuery<QualityProfile[], ApiError>({
    queryKey: QUALITY_PROFILES_KEY,
    queryFn: () => apiFetch<QualityProfile[]>("/api/v3/qualityprofile"),
    staleTime: 30_000,
  });
}

export function useDeleteQualityProfile(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/qualityprofile/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUALITY_PROFILES_KEY });
    },
  });
}
