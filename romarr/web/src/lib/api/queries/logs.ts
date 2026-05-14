/**
 * Settings → Logs page query hook (slice 392).
 *
 * Wraps ``GET /api/v3/system/log`` — the in-memory ring-buffer
 * reader installed at app startup. Auto-refetches every 5 s so
 * the operator sees live activity without reloading.
 */

import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

export type LogLevel = "debug" | "info" | "warn" | "error" | "fatal";

export interface LogEntry {
  id: number;
  time: string;
  level: LogLevel;
  logger: string;
  message: string;
  exception?: string | null;
  exceptionType?: string | null;
}

export interface LogsEnvelope {
  page: number;
  pageSize: number;
  sortKey: string;
  sortDirection: "asc" | "desc";
  totalRecords: number;
  records: LogEntry[];
}

export interface UseLogsParams {
  page?: number;
  pageSize?: number;
  level?: LogLevel | null;
  logger?: string | null;
}

export function useLogs(
  params: UseLogsParams = {},
): UseQueryResult<LogsEnvelope, ApiError> {
  const search = new URLSearchParams();
  search.set("page", String(params.page ?? 1));
  search.set("pageSize", String(params.pageSize ?? 100));
  if (params.level) search.set("level", params.level);
  if (params.logger && params.logger.trim().length > 0) {
    search.set("logger", params.logger.trim());
  }
  return useQuery<LogsEnvelope, ApiError>({
    queryKey: ["settings", "logs", params],
    queryFn: () =>
      apiFetch<LogsEnvelope>(`/api/v3/system/log?${search.toString()}`),
    refetchInterval: 5_000,
    staleTime: 0,
  });
}
