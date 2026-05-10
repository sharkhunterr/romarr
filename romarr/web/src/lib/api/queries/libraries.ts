/**
 * Library read + delete TanStack Query hooks (slice 92).
 *
 * Wraps spec 009 /api/v3/rom/library:
 *   * GET    /api/v3/rom/library
 *   * GET    /api/v3/rom/library/{id}
 *   * DELETE /api/v3/rom/library/{id}?force=true
 *
 * Create + update flows are deferred to a follow-up slice —
 * LibraryCreate carries many required FKs (the 5 profile
 * bindings + lifecycle policy + paths) that deserve a
 * multi-step form.
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

export type Library = components["schemas"]["LibraryRead"];

export type LibraryLifecyclePolicy =
  | "hardlink_and_seed"
  | "move_and_remove"
  | "copy_and_keep";

/**
 * ``POST /api/v3/rom/library`` body. The OpenAPI codegen leaves
 * the request shape as ``{[key: string]: unknown}`` because the
 * backend's pydantic model includes a ``SecretStr`` field for
 * the RomM API key; we mirror the documented schema here so the
 * Add-library modal has a typed contract to fill.
 */
export interface LibraryCreate {
  name: string;
  path: string;
  platform_subfolders?: boolean;
  platforms_restricted?: boolean;
  platform_ids?: number[];
  quality_profile_id: number;
  region_profile_id: number;
  dump_profile_id: number;
  language_profile_id: number;
  naming_profile_id: number;
  monitored_default?: boolean;
  use_hardlinks?: boolean;
  lifecycle_policy?: LibraryLifecyclePolicy;
  delete_after_import?: boolean;
  keep_dump_history?: boolean;
  min_disk_free_gb?: number;
  preserve_archive?: boolean;
  exporter_romm_enabled?: boolean;
  exporter_romm_url?: string | null;
  exporter_romm_api_key?: string | null;
  exporter_esde_enabled?: boolean;
  exporter_pegasus_enabled?: boolean;
  exporter_launchbox_enabled?: boolean;
  exporter_launchbox_per_platform?: boolean;
  scan_poll_seconds?: number;
  heartbeat_seconds?: number;
}

const KEY = ["settings", "libraries"] as const;

export function useLibraries(): UseQueryResult<Library[], ApiError> {
  return useQuery<Library[], ApiError>({
    queryKey: KEY,
    queryFn: () => apiFetch<Library[]>("/api/v3/rom/library"),
    staleTime: 30_000,
  });
}

export function useCreateLibrary(): UseMutationResult<
  Library,
  ApiError,
  LibraryCreate
> {
  const qc = useQueryClient();
  return useMutation<Library, ApiError, LibraryCreate>({
    mutationFn: (payload) =>
      apiFetch<Library>("/api/v3/rom/library", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export interface UpdateLibraryVariables {
  id: number;
  payload: Partial<LibraryCreate>;
}

export function useUpdateLibrary(): UseMutationResult<
  Library,
  ApiError,
  UpdateLibraryVariables
> {
  const qc = useQueryClient();
  return useMutation<Library, ApiError, UpdateLibraryVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<Library>(`/api/v3/rom/library/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export interface DeleteLibraryVariables {
  id: number;
  /**
   * Cascade-detach Releases before deleting (`?force=true`
   * on the server). Default is false; the API returns 409
   * with errorCode `library_has_releases` when this isn't
   * set and Releases reference the library.
   */
  force?: boolean;
}

export function useDeleteLibrary(): UseMutationResult<
  void,
  ApiError,
  DeleteLibraryVariables
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, DeleteLibraryVariables>({
    mutationFn: ({ id, force }) =>
      apiFetch<void>(
        `/api/v3/rom/library/${id}${force ? "?force=true" : ""}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
