/**
 * System-page TanStack Query hooks (logs, backups, tasks).
 *
 * The Status tab reuses the slice 47 ``useSystemStatus`` hook
 * from `@/lib/api/queries/system`; this module covers the
 * three list endpoints unique to the System page.
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

/**
 * Live polling on the tasks list — refetches every 3 s while
 * any job is in flight (``current_run_id`` non-null), then
 * pauses. Drives the Activity → Tasks banner so the operator
 * watches a scan / metadata refresh advance without manually
 * reloading.
 */
export function useActiveTasks(): UseQueryResult<Job[], ApiError> {
  return useQuery<Job[], ApiError>({
    queryKey: ["system", "tasks", "active"],
    queryFn: () => apiFetch<Job[]>("/api/v3/system/tasks"),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data === undefined) return 3_000;
      return data.some((j) => j.current_run_id != null) ? 3_000 : false;
    },
    staleTime: 2_000,
  });
}

export interface CancelRunVariables {
  jobId: string;
  runId: number;
  force?: boolean;
}

/** Cooperative cancel — signals the running task to stop at its
 * next checkpoint. ``force=true`` skips the grace window. */
export function useCancelTaskRun(): UseMutationResult<
  void,
  ApiError,
  CancelRunVariables
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, CancelRunVariables>({
    mutationFn: ({ jobId, runId, force }) =>
      apiFetch<void>(
        `/api/v3/system/tasks/${jobId}/runs/${runId}/cancel${force ? "?force=true" : ""}`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["system", "tasks"] });
    },
  });
}

// Re-export the row types so the page components can type
// their props without re-deriving them.
export type { BackupFileEntry, Job, LogFileEntry };
