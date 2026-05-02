/**
 * System-page TanStack Query hooks (logs, backups, tasks).
 *
 * The Status tab reuses the slice 47 ``useSystemStatus`` hook
 * from `@/lib/api/queries/system`; this module covers the
 * three list endpoints unique to the System page.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

// ---------------------------------------------------------------------------
// Logs — GET /api/v3/system/log/file
// ---------------------------------------------------------------------------

type LogFileEntry = components["schemas"]["LogFileEntry"];

export function useLogFiles(): UseQueryResult<LogFileEntry[], ApiError> {
  return useQuery<LogFileEntry[], ApiError>({
    queryKey: ["system", "log", "file"],
    queryFn: () => apiFetch<LogFileEntry[]>("/api/v3/system/log/file"),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// Backups — GET /api/v3/system/backup
// ---------------------------------------------------------------------------

type BackupFileEntry = components["schemas"]["BackupFileEntry"];

export function useBackups(): UseQueryResult<BackupFileEntry[], ApiError> {
  return useQuery<BackupFileEntry[], ApiError>({
    queryKey: ["system", "backup"],
    queryFn: () => apiFetch<BackupFileEntry[]>("/api/v3/system/backup"),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Tasks (scheduled jobs) — GET /api/v3/system/tasks
// ---------------------------------------------------------------------------

type Job = components["schemas"]["JobRead"];

export function useTasks(): UseQueryResult<Job[], ApiError> {
  return useQuery<Job[], ApiError>({
    queryKey: ["system", "tasks"],
    queryFn: () => apiFetch<Job[]>("/api/v3/system/tasks"),
    staleTime: 30_000,
  });
}

// Re-export the row types so the page components can type
// their props without re-deriving them.
export type { BackupFileEntry, Job, LogFileEntry };
