/**
 * Community Update Center hooks.
 *
 * Backs the header UpdateCenterBadge (aggregated feed) and the
 * Settings > Update Center panel (per-source CRUD + check + apply).
 * All endpoints under /api/v3/community/*.
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

export type CommunitySource = components["schemas"]["SourceRead"];
export type CommunityUpdatesFeed = components["schemas"]["UpdatesFeed"];
export type CheckResponse = components["schemas"]["CheckResponse"];
export type ApplyResponse = components["schemas"]["ApplyResponse"];
export type PreviewResponse = components["schemas"]["PreviewResponse"];

export type CommunityResourceType = "platform_pack" | "custom_format";

const SOURCES_KEY = ["community", "sources"] as const;
const FEED_KEY = ["community", "updates"] as const;

// ---------------------------------------------------------------------------
// Aggregated updates feed — the badge + popover read this
// ---------------------------------------------------------------------------

/**
 * ``GET /api/v3/community/updates`` — Romarr GitHub release check
 * + every community source in one payload. Backend caches the
 * GitHub half for 1 h; the community half reads from DB
 * (updated by the sync engine). Polls every 30 min in the client.
 */
export function useCommunityUpdatesFeed(): UseQueryResult<
  CommunityUpdatesFeed,
  ApiError
> {
  return useQuery<CommunityUpdatesFeed, ApiError>({
    queryKey: FEED_KEY,
    queryFn: () => apiFetch<CommunityUpdatesFeed>("/api/v3/community/updates"),
    staleTime: 30 * 60_000,
    refetchOnWindowFocus: false,
  });
}

// ---------------------------------------------------------------------------
// Sources list (Settings > Update Center panel)
// ---------------------------------------------------------------------------

export function useCommunitySources(
  resourceType?: CommunityResourceType,
): UseQueryResult<CommunitySource[], ApiError> {
  return useQuery<CommunitySource[], ApiError>({
    queryKey: resourceType
      ? [...SOURCES_KEY, resourceType]
      : SOURCES_KEY,
    queryFn: () => {
      const qs = resourceType ? `?resource_type=${resourceType}` : "";
      return apiFetch<CommunitySource[]>(`/api/v3/community/source${qs}`);
    },
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export interface CreateSourceVars {
  name: string;
  url: string;
  resourceType: CommunityResourceType;
  kind?: "raw" | "github_dir";
}

export function useCreateCommunitySource(): UseMutationResult<
  CheckResponse,
  ApiError,
  CreateSourceVars
> {
  const qc = useQueryClient();
  return useMutation<CheckResponse, ApiError, CreateSourceVars>({
    mutationFn: ({ name, url, resourceType, kind }) =>
      apiFetch<CheckResponse>("/api/v3/community/source", {
        method: "POST",
        json: {
          name,
          url,
          resource_type: resourceType,
          kind: kind ?? "raw",
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
    },
  });
}

export interface PatchSourceVars {
  sourceId: number;
  enabled?: boolean;
  autoCheck?: boolean;
  trustStatus?: "pending" | "trusted";
  name?: string;
  url?: string;
}

export function usePatchCommunitySource(): UseMutationResult<
  CommunitySource,
  ApiError,
  PatchSourceVars
> {
  const qc = useQueryClient();
  return useMutation<CommunitySource, ApiError, PatchSourceVars>({
    mutationFn: ({ sourceId, enabled, autoCheck, trustStatus, name, url }) => {
      const body: Record<string, unknown> = {};
      if (enabled !== undefined) body.enabled = enabled;
      if (autoCheck !== undefined) body.auto_check = autoCheck;
      if (trustStatus !== undefined) body.trust_status = trustStatus;
      if (name !== undefined) body.name = name;
      if (url !== undefined) body.url = url;
      return apiFetch<CommunitySource>(
        `/api/v3/community/source/${sourceId}`,
        { method: "PATCH", json: body },
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
    },
  });
}

export function useDeleteCommunitySource(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (sourceId) =>
      apiFetch<void>(`/api/v3/community/source/${sourceId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
    },
  });
}

export function useCheckCommunitySource(): UseMutationResult<
  CheckResponse,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<CheckResponse, ApiError, number>({
    mutationFn: (sourceId) =>
      apiFetch<CheckResponse>(
        `/api/v3/community/source/${sourceId}/check`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
    },
  });
}

export function usePreviewCommunitySource(): UseMutationResult<
  PreviewResponse,
  ApiError,
  number
> {
  return useMutation<PreviewResponse, ApiError, number>({
    mutationFn: (sourceId) =>
      apiFetch<PreviewResponse>(
        `/api/v3/community/source/${sourceId}/preview`,
        { method: "POST" },
      ),
  });
}

export function useApplyCommunitySource(): UseMutationResult<
  ApplyResponse,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<ApplyResponse, ApiError, number>({
    mutationFn: (sourceId) =>
      apiFetch<ApplyResponse>(
        `/api/v3/community/source/${sourceId}/apply`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
      void qc.invalidateQueries({ queryKey: ["custom-formats"] });
      void qc.invalidateQueries({ queryKey: ["platforms"] });
    },
  });
}
