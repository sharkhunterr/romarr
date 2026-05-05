/**
 * Naming-profile read + delete + preview hooks.
 *
 * Slice 91 shipped read + delete; slice 273 wires the live
 * preview against ``POST /api/v3/rom/namingprofile/preview``
 * for the Profiles > Naming tab template editor.
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
export type NamingProfileCreate =
  components["schemas"]["NamingProfileCreate"];
export type NamingPreviewResponse =
  components["schemas"]["NamingPreviewResponse"];

export interface NamingPreviewVariables {
  profile: NamingProfileCreate;
  /**
   * Sample release id. The backend currently uses synthetic
   * sample data (Sonic the Hedgehog (USA).md) regardless of
   * this id, but the field is required by the contract; pass
   * any positive integer.
   */
  sample_release_id?: number;
}

const KEY = ["settings", "naming-profiles"] as const;

export function useNamingProfiles(): UseQueryResult<NamingProfile[], ApiError> {
  return useQuery<NamingProfile[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<NamingProfile[]>("/api/v3/rom/namingprofile"),
    staleTime: 30_000,
  });
}

export function useCreateNamingProfile(): UseMutationResult<
  NamingProfile,
  ApiError,
  NamingProfileCreate
> {
  const qc = useQueryClient();
  return useMutation<NamingProfile, ApiError, NamingProfileCreate>({
    mutationFn: (payload) =>
      apiFetch<NamingProfile>("/api/v3/rom/namingprofile", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
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

export function useNamingPreview(): UseMutationResult<
  NamingPreviewResponse,
  ApiError,
  NamingPreviewVariables
> {
  return useMutation<NamingPreviewResponse, ApiError, NamingPreviewVariables>({
    mutationFn: (vars) =>
      apiFetch<NamingPreviewResponse>("/api/v3/rom/namingprofile/preview", {
        method: "POST",
        json: {
          profile: vars.profile,
          sample_release_id: vars.sample_release_id ?? 1,
        },
      }),
  });
}
