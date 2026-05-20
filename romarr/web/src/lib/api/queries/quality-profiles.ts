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

/**
 * ``POST /api/v3/qualityprofile`` body. The OpenAPI codegen
 * leaves the request body untyped (see the LibraryCreate
 * comment); we mirror the documented backend pydantic model so
 * the create modal has a typed contract.
 */
export interface QualityProfileCreate {
  name: string;
  allowed_formats: string[];
  preferred_format: string;
  upgrade_until_format: string;
  require_dat_verified?: boolean;
  allow_archive_double_compression?: boolean;
  /** Floor for RSS + on-add auto-grab. Manual grabs ignore it. */
  auto_grab_min_score?: number;
}

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

export function useCreateQualityProfile(): UseMutationResult<
  QualityProfile,
  ApiError,
  QualityProfileCreate
> {
  const qc = useQueryClient();
  return useMutation<QualityProfile, ApiError, QualityProfileCreate>({
    mutationFn: (payload) =>
      apiFetch<QualityProfile>("/api/v3/qualityprofile", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUALITY_PROFILES_KEY });
    },
  });
}

export interface UpdateQualityProfileVariables {
  id: number;
  payload: Partial<QualityProfileCreate>;
}

export function useUpdateQualityProfile(): UseMutationResult<
  QualityProfile,
  ApiError,
  UpdateQualityProfileVariables
> {
  const qc = useQueryClient();
  return useMutation<QualityProfile, ApiError, UpdateQualityProfileVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<QualityProfile>(`/api/v3/qualityprofile/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUALITY_PROFILES_KEY });
    },
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
