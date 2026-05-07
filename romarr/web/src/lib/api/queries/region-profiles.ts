/**
 * Region-profile read + delete hooks (slice 90).
 *
 * Same pattern as quality-profiles.ts (slice 65). Read +
 * delete only — full editor (priorities drag-list +
 * exclude-regions multi-select) lands in a follow-up slice.
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

export type RegionProfile = components["schemas"]["RegionProfileRead"];

export interface RegionProfileCreate {
  name: string;
  priorities: string[];
  exclude_regions: string[];
  allow_fallback_outside_priorities?: boolean;
}

export type RegionProfileUpdate = Partial<RegionProfileCreate>;

const KEY = ["settings", "region-profiles"] as const;

export function useRegionProfiles(): UseQueryResult<
  RegionProfile[],
  ApiError
> {
  return useQuery<RegionProfile[], ApiError>({
    queryKey: KEY,
    queryFn: () =>
      apiFetch<RegionProfile[]>("/api/v3/rom/regionprofile"),
    staleTime: 30_000,
  });
}

export function useCreateRegionProfile(): UseMutationResult<
  RegionProfile,
  ApiError,
  RegionProfileCreate
> {
  const qc = useQueryClient();
  return useMutation<RegionProfile, ApiError, RegionProfileCreate>({
    mutationFn: (payload) =>
      apiFetch<RegionProfile>("/api/v3/rom/regionprofile", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useUpdateRegionProfile(): UseMutationResult<
  RegionProfile,
  ApiError,
  { id: number; payload: RegionProfileUpdate }
> {
  const qc = useQueryClient();
  return useMutation<
    RegionProfile,
    ApiError,
    { id: number; payload: RegionProfileUpdate }
  >({
    mutationFn: ({ id, payload }) =>
      apiFetch<RegionProfile>(`/api/v3/rom/regionprofile/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeleteRegionProfile(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom/regionprofile/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
