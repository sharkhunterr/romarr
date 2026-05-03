/**
 * Wanted-page TanStack Query hooks.
 *
 * Two endpoints from spec 013 phase ROUTERS:
 *   * GET /api/v3/wanted/missing — releases the operator has
 *     flagged monitored but Romarr hasn't acquired yet.
 *   * GET /api/v3/wanted/cutoff — imported releases that
 *     don't yet meet the configured upgrade cutoff.
 *
 * Both return the canonical PaginationEnvelope with
 * WantedReleaseRead records (camelCase Sonarr-shape).
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type WantedRelease = components["schemas"]["WantedReleaseRead"];

interface WantedEnvelope {
  page: number;
  pageSize: number;
  sortKey: string;
  sortDirection: string;
  totalRecords: number;
  records: WantedRelease[];
}

export interface UseWantedParams {
  page?: number;
  pageSize?: number;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  /** Restrict to a single platform (joined via Game). */
  platformId?: number;
  /**
   * Restrict to releases whose joined Game carries this tag id
   * (slice 157, matched against Game.tags JSON list).
   */
  tagId?: number;
  /** Case-insensitive substring filter on Release.name. */
  q?: string;
}

function buildQueryString(params: UseWantedParams): string {
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined)
    search.set("pageSize", String(params.pageSize));
  if (params.sortKey !== undefined) search.set("sortKey", params.sortKey);
  if (params.sortDirection !== undefined)
    search.set("sortDirection", params.sortDirection);
  if (params.platformId !== undefined)
    search.set("platformId", String(params.platformId));
  if (params.tagId !== undefined)
    search.set("tagId", String(params.tagId));
  if (params.q !== undefined && params.q.trim() !== "")
    search.set("q", params.q.trim());
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function useWantedMissing(
  params: UseWantedParams = {},
): UseQueryResult<WantedEnvelope, ApiError> {
  return useQuery<WantedEnvelope, ApiError>({
    queryKey: ["wanted", "missing", params],
    queryFn: () =>
      apiFetch<WantedEnvelope>(
        `/api/v3/wanted/missing${buildQueryString(params)}`,
      ),
    staleTime: 30_000,
  });
}

export function useWantedCutoff(
  params: UseWantedParams = {},
): UseQueryResult<WantedEnvelope, ApiError> {
  return useQuery<WantedEnvelope, ApiError>({
    queryKey: ["wanted", "cutoff", params],
    queryFn: () =>
      apiFetch<WantedEnvelope>(
        `/api/v3/wanted/cutoff${buildQueryString(params)}`,
      ),
    staleTime: 30_000,
  });
}
