/**
 * Platform-pack read hooks (slice 93).
 *
 * Wraps spec 003 /api/v3/rom/platform-pack:
 *   * GET /api/v3/rom/platform-pack          — list applied packs
 *   * GET /api/v3/rom/platform-pack/{version} — detail + history
 *
 * Upload + re-apply are admin write flows; deferred to a
 * follow-up slice that adds a multipart upload form.
 */

import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type PackSummary = components["schemas"]["PackSummary"];
export type PackDetail = components["schemas"]["PackDetail"];
export type PackHistoryRow = components["schemas"]["PackHistoryRow"];

const ROOT_KEY = ["settings", "platform-packs"] as const;

export function usePlatformPacks(): UseQueryResult<PackSummary[], ApiError> {
  return useQuery<PackSummary[], ApiError>({
    queryKey: ROOT_KEY,
    queryFn: () => apiFetch<PackSummary[]>("/api/v3/rom/platform-pack"),
    staleTime: 30_000,
  });
}

export function usePlatformPack(
  packVersion: string | null,
): UseQueryResult<PackDetail, ApiError> {
  return useQuery<PackDetail, ApiError>({
    queryKey: [...ROOT_KEY, packVersion ?? ""],
    queryFn: () =>
      apiFetch<PackDetail>(
        `/api/v3/rom/platform-pack/${encodeURIComponent(packVersion ?? "")}`,
      ),
    enabled: packVersion !== null && packVersion !== "",
    staleTime: 30_000,
  });
}
