/**
 * DAT-sources API hooks (slices 267 + 444).
 *
 * Two surfaces:
 * - ``GET /api/v3/dat-source`` — cache summary grouped by source
 *   name (No-Intro / Redump / TOSEC / etc.). Read-only.
 * - ``/api/v3/dat-source/sources`` — full CRUD over the
 *   ``dat_source`` table introduced by slice 443: list, create,
 *   update, delete, refresh-one, refresh-all. Operator-facing.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

// ---- summary (legacy contract) ----------------------------------------

export interface DatSourceSummary {
  source: string;
  entry_count: number;
  platform_count: number;
  latest_updated_at: string | null;
}

const SUMMARY_KEY = ["settings", "dat-sources", "summary"] as const;

export function useDatSources(): UseQueryResult<DatSourceSummary[], ApiError> {
  return useQuery<DatSourceSummary[], ApiError>({
    queryKey: SUMMARY_KEY,
    queryFn: () => apiFetch<DatSourceSummary[]>("/api/v3/dat-source"),
    staleTime: 5 * 60_000,
  });
}

// ---- per-row CRUD (slice 444) -----------------------------------------

export type DatAuthoritySource =
  | "no-intro"
  | "redump"
  | "tosec"
  | "goodtools"
  | "hasheous"
  | "playmatch"
  | "custom";

export type DatRefreshStatus = "ok" | "failed" | "running";

export interface DatSourceRead {
  id: number;
  name: string;
  url: string;
  source: DatAuthoritySource;
  platform_id: number;
  platform_slug: string | null;
  platform_name: string | null;
  enabled: boolean;
  last_refresh_at: string | null;
  last_refresh_status: DatRefreshStatus | null;
  last_refresh_error: string | null;
  last_entry_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface DatSourceCreate {
  name: string;
  url: string;
  source: DatAuthoritySource;
  platform_id: number;
  enabled?: boolean;
}

export interface DatSourceUpdate {
  name?: string;
  url?: string;
  enabled?: boolean;
}

export interface DatRefreshOutcome {
  id: number;
  name: string;
  status: DatRefreshStatus;
  entries_ingested?: number | null;
  error?: string | null;
}

const SOURCES_KEY = ["settings", "dat-sources", "sources"] as const;

/** Invalidate every dat-sources-related cache after a mutation. */
function _invalidateAll(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: SOURCES_KEY });
  void qc.invalidateQueries({ queryKey: SUMMARY_KEY });
}

export function useDatSourceRows(): UseQueryResult<DatSourceRead[], ApiError> {
  return useQuery<DatSourceRead[], ApiError>({
    queryKey: SOURCES_KEY,
    queryFn: () => apiFetch<DatSourceRead[]>("/api/v3/dat-source/sources"),
    staleTime: 30_000,
  });
}

export function useCreateDatSource(): UseMutationResult<
  DatSourceRead,
  ApiError,
  DatSourceCreate
> {
  const qc = useQueryClient();
  return useMutation<DatSourceRead, ApiError, DatSourceCreate>({
    mutationFn: (payload) =>
      apiFetch<DatSourceRead>("/api/v3/dat-source/sources", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => _invalidateAll(qc),
  });
}

export interface UpdateDatSourceVariables {
  id: number;
  payload: DatSourceUpdate;
}

export function useUpdateDatSource(): UseMutationResult<
  DatSourceRead,
  ApiError,
  UpdateDatSourceVariables
> {
  const qc = useQueryClient();
  return useMutation<DatSourceRead, ApiError, UpdateDatSourceVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<DatSourceRead>(`/api/v3/dat-source/sources/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => _invalidateAll(qc),
  });
}

export function useDeleteDatSource(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/dat-source/sources/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => _invalidateAll(qc),
  });
}

export function useRefreshDatSource(): UseMutationResult<
  DatRefreshOutcome,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<DatRefreshOutcome, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<DatRefreshOutcome>(
        `/api/v3/dat-source/sources/${id}/refresh`,
        { method: "POST" },
      ),
    onSuccess: () => _invalidateAll(qc),
  });
}

export function useRefreshAllDatSources(): UseMutationResult<
  DatRefreshOutcome[],
  ApiError,
  void
> {
  const qc = useQueryClient();
  return useMutation<DatRefreshOutcome[], ApiError, void>({
    mutationFn: () =>
      apiFetch<DatRefreshOutcome[]>(
        "/api/v3/dat-source/sources/refresh-all",
        { method: "POST" },
      ),
    onSuccess: () => _invalidateAll(qc),
  });
}
