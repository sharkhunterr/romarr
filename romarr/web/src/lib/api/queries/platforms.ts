/**
 * Platform read hook (slice 99).
 *
 * Wraps the spec-003 catalogue endpoint:
 *   * GET /api/v3/rom/platform — list every platform.
 *
 * The full list is small (a few dozen rows at most, even with
 * the future community packs), so we fetch it once and cache
 * for 5 minutes. Consumers index it by id via the
 * `usePlatformsById` selector helper.
 */

import { useMemo } from "react";
import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type Platform = components["schemas"]["PlatformRead"];

const KEY = ["platforms", "list"] as const;

export function usePlatforms(): UseQueryResult<Platform[], ApiError> {
  return useQuery<Platform[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<Platform[]>("/api/v3/rom/platform"),
    staleTime: 5 * 60_000,
  });
}

/**
 * Lookup helper — id → Platform. Returns an empty Map until
 * the underlying query resolves. Memoised on the query result
 * so consumers don't rebuild the index on every render.
 */
export function usePlatformsById(): Map<number, Platform> {
  const platforms = usePlatforms();
  return useMemo(() => {
    const out = new Map<number, Platform>();
    for (const p of platforms.data ?? []) {
      out.set(p.id, p);
    }
    return out;
  }, [platforms.data]);
}
