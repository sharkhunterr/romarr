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
export type BindingRead = components["schemas"]["BindingRead"];
export type BindingMode = BindingRead["mode"];
export type SourceOrderRead = components["schemas"]["SourceOrderRead"];

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

// ---------------------------------------------------------------------------
// Bindings — per-(source, platform) overrides. Today only mode='skip' honoured.
// ---------------------------------------------------------------------------

const BINDINGS_KEY = ["community", "bindings"] as const;

export function useCommunitySourceBindings(
  sourceId: number | null,
): UseQueryResult<BindingRead[], ApiError> {
  return useQuery<BindingRead[], ApiError>({
    queryKey: [...BINDINGS_KEY, sourceId],
    queryFn: () =>
      apiFetch<BindingRead[]>(
        `/api/v3/community/source/${sourceId}/binding`,
      ),
    enabled: sourceId !== null,
    staleTime: 60_000,
  });
}

export interface ReplaceBindingsVars {
  sourceId: number;
  bindings: BindingRead[];
}

export function useReplaceCommunitySourceBindings(): UseMutationResult<
  BindingRead[],
  ApiError,
  ReplaceBindingsVars
> {
  const qc = useQueryClient();
  return useMutation<BindingRead[], ApiError, ReplaceBindingsVars>({
    mutationFn: ({ sourceId, bindings }) =>
      apiFetch<BindingRead[]>(
        `/api/v3/community/source/${sourceId}/binding`,
        { method: "PUT", json: { bindings } },
      ),
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({
        queryKey: [...BINDINGS_KEY, vars.sourceId],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Global source order — used by platform materialize to break scalar ties
// ---------------------------------------------------------------------------

const SOURCE_ORDER_KEY = ["community", "source-order"] as const;

export function useSourceOrder(): UseQueryResult<SourceOrderRead, ApiError> {
  return useQuery<SourceOrderRead, ApiError>({
    queryKey: SOURCE_ORDER_KEY,
    queryFn: () => apiFetch<SourceOrderRead>("/api/v3/community/source-order"),
    staleTime: 60_000,
  });
}

export function useReplaceSourceOrder(): UseMutationResult<
  SourceOrderRead,
  ApiError,
  number[]
> {
  const qc = useQueryClient();
  return useMutation<SourceOrderRead, ApiError, number[]>({
    mutationFn: (sourceIds) =>
      apiFetch<SourceOrderRead>("/api/v3/community/source-order", {
        method: "PUT",
        json: { source_order: sourceIds },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCE_ORDER_KEY });
      void qc.invalidateQueries({ queryKey: ["platforms"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Local file import — for air-gapped installs
// ---------------------------------------------------------------------------

export interface ImportSourceVars {
  file: File;
  name?: string;
}

export function useImportCommunitySource(): UseMutationResult<
  ApplyResponse,
  ApiError,
  ImportSourceVars
> {
  const qc = useQueryClient();
  return useMutation<ApplyResponse, ApiError, ImportSourceVars>({
    mutationFn: async ({ file, name }) => {
      const form = new FormData();
      form.append("file", file);
      if (name) form.append("name", name);
      // apiFetch normally sets Content-Type: application/json.
      // For multipart we use fetch directly and rely on the
      // browser to set the boundary.
      const resp = await fetch(
        `/api/v3/community/source/import${name ? `?name=${encodeURIComponent(name)}` : ""}`,
        { method: "POST", body: form, credentials: "include" },
      );
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const body = await resp.json();
          if (body?.detail?.errorMessage) msg = body.detail.errorMessage;
          else if (body?.errorMessage) msg = body.errorMessage;
        } catch {
          /* ignore parse errors */
        }
        throw new ApiError(resp.status, { errorMessage: msg });
      }
      return (await resp.json()) as ApplyResponse;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SOURCES_KEY });
      void qc.invalidateQueries({ queryKey: FEED_KEY });
      void qc.invalidateQueries({ queryKey: ["custom-formats"] });
      void qc.invalidateQueries({ queryKey: ["platforms"] });
    },
  });
}
