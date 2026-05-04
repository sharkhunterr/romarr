/**
 * Quality-definitions read hook (slice 266).
 *
 * Wraps ``GET /api/v3/quality-definition`` — the read-only
 * aggregate of every Platform + its PlatformFormat rows.
 * Drives the Settings > Quality Definitions table.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

export interface QualityDefinitionFormat {
  id: number;
  extension: string;
  format_type: string;
  min_size_bytes: number | null;
  max_size_bytes: number | null;
  pack_source: string;
}

export interface QualityDefinitionPlatform {
  platform_id: number;
  platform_slug: string;
  platform_name: string;
  formats: QualityDefinitionFormat[];
}

const KEY = ["settings", "quality-definitions"] as const;

export function useQualityDefinitions(): UseQueryResult<
  QualityDefinitionPlatform[],
  ApiError
> {
  return useQuery<QualityDefinitionPlatform[], ApiError>({
    queryKey: KEY,
    queryFn: () =>
      apiFetch<QualityDefinitionPlatform[]>("/api/v3/quality-definition"),
    staleTime: 5 * 60_000,
  });
}
