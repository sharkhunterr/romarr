/**
 * System-level TanStack Query hooks (status / health / history /
 * command).
 *
 * These power the Dashboard. The list endpoints
 * (history) consume the canonical PaginationEnvelope shape
 * spec 013 ships; the system/status response is a free-form
 * dict[str, Any] (see backend/spec 013 OPENAPI customizer
 * notes).
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

// ---------------------------------------------------------------------------
// /api/v3/system/status — Sonarr-shape system info
// ---------------------------------------------------------------------------

export interface SystemStatus {
  version: string;
  isProduction: boolean;
  // Authenticated tier — these are present once auth resolves.
  instanceName?: string;
  urlBase?: string;
  osName?: string;
  runtimeVersion?: string;
  appData?: string;
  startTime?: string;
  databaseType?: string;
  databaseVersion?: string;
  migrationVersion?: string;
  runtimeName?: string;
  // The endpoint may add more fields over time; let the type
  // stay open so a backend addition doesn't trip the build.
  [key: string]: unknown;
}

export const SYSTEM_STATUS_KEY = ["system", "status"] as const;

export function useSystemStatus(): UseQueryResult<SystemStatus, ApiError> {
  return useQuery<SystemStatus, ApiError>({
    queryKey: SYSTEM_STATUS_KEY,
    queryFn: () => apiFetch<SystemStatus>("/api/v3/system/status"),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// /api/v3/health — health snapshot (loosely typed)
// ---------------------------------------------------------------------------

export type HealthStatus = "ok" | "warning" | "error";

export interface HealthEntry {
  category?: string;
  level?: HealthStatus | string;
  message?: string;
  [key: string]: unknown;
}

export interface HealthSnapshot {
  status: HealthStatus;
  entries?: HealthEntry[];
  [key: string]: unknown;
}

export const HEALTH_KEY = ["system", "health"] as const;

export function useHealth(): UseQueryResult<HealthSnapshot, ApiError> {
  return useQuery<HealthSnapshot, ApiError>({
    queryKey: HEALTH_KEY,
    queryFn: () => apiFetch<HealthSnapshot>("/api/v3/health"),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// /api/v3/system/stats — Dashboard aggregate counts (slice 104)
// ---------------------------------------------------------------------------

export type SystemStats = components["schemas"]["SystemStats"];

export const SYSTEM_STATS_KEY = ["system", "stats"] as const;

export function useSystemStats(): UseQueryResult<SystemStats, ApiError> {
  return useQuery<SystemStats, ApiError>({
    queryKey: SYSTEM_STATS_KEY,
    queryFn: () => apiFetch<SystemStats>("/api/v3/system/stats"),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// /api/v3/history — unified history feed (paginated)
// ---------------------------------------------------------------------------

type HistoryEvent = components["schemas"]["HistoryEvent"];

interface HistoryEnvelope {
  page: number;
  pageSize: number;
  sortKey: string;
  sortDirection: string;
  totalRecords: number;
  records: HistoryEvent[];
}

export const HISTORY_KEY = ["system", "history"] as const;

export type HistoryEventType = "import" | "search" | "job_run";

export interface UseHistoryParams {
  page?: number;
  pageSize?: number;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  /**
   * Filter to a single game's audit trail. Job-run rows (which
   * carry no `gameId`) are excluded server-side when this is set.
   */
  gameId?: number;
  /** Filter to one of the three documented event types. */
  eventType?: HistoryEventType;
  /**
   * Filter on the derived `successful` flag. `false` is the most
   * common operator workflow ("show me failures").
   */
  successful?: boolean;
  /** ISO-8601 datetime; only entries with `date >= since`. */
  since?: string;
}

export function useHistory(
  params: UseHistoryParams = {},
): UseQueryResult<HistoryEnvelope, ApiError> {
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined)
    search.set("pageSize", String(params.pageSize));
  if (params.sortKey !== undefined) search.set("sortKey", params.sortKey);
  if (params.sortDirection !== undefined)
    search.set("sortDirection", params.sortDirection);
  if (params.gameId !== undefined) search.set("gameId", String(params.gameId));
  if (params.eventType !== undefined)
    search.set("eventType", params.eventType);
  if (params.successful !== undefined)
    search.set("successful", String(params.successful));
  if (params.since !== undefined) search.set("since", params.since);
  const qs = search.toString();

  return useQuery<HistoryEnvelope, ApiError>({
    queryKey: [...HISTORY_KEY, params],
    queryFn: () =>
      apiFetch<HistoryEnvelope>(
        `/api/v3/history${qs ? `?${qs}` : ""}`,
      ),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// /api/v3/command — fire a Sonarr-shape command by name
// ---------------------------------------------------------------------------

export interface CommandPayload {
  name: string;
  [key: string]: unknown;
}

interface CommandResponse {
  id: number;
  name: string;
  status: string;
  [key: string]: unknown;
}

export function useTriggerCommand(): UseMutationResult<
  CommandResponse,
  ApiError,
  CommandPayload
> {
  const qc = useQueryClient();
  return useMutation<CommandResponse, ApiError, CommandPayload>({
    mutationFn: (payload) =>
      apiFetch<CommandResponse>("/api/v3/command", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      // History feed picks up a new "job_run" event when the
      // scheduler emits it — invalidate so the dashboard
      // updates immediately.
      void qc.invalidateQueries({ queryKey: HISTORY_KEY });
    },
  });
}
