/**
 * ROM content-pack API hooks (slice 461).
 *
 * Wraps the ``/api/v3/rom-pack`` surface:
 * - list / get / per-item outcomes (read);
 * - create / update / delete (operator-facing CRUD);
 * - ``/ingest`` — fires the download → extract → import pipeline
 *   as a detached task. The pack row's ``status`` + counter
 *   fields are the progress channel; the list query polls while
 *   any pack is mid-run.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

export type RomPackSourceKind = "url" | "grab";

export type RomPackStatus =
  | "pending"
  | "downloading"
  | "extracting"
  | "importing"
  | "awaiting_triage"
  | "done"
  | "failed";

export type RomPackItemStatus =
  | "imported"
  | "unmatched"
  | "parked"
  | "deleted"
  | "failed";

/** Statuses where the ingest pipeline is actively working —
 * the list query polls while any pack is in one of these. */
export const ROM_PACK_BUSY_STATUSES: ReadonlySet<RomPackStatus> = new Set([
  "pending",
  "downloading",
  "extracting",
  "importing",
]);

export interface RomPackRead {
  id: number;
  name: string;
  source_kind: RomPackSourceKind;
  url: string | null;
  download_client_id: number | null;
  download_client_native_id: string | null;
  platform_id: number | null;
  platform_slug: string | null;
  platform_name: string | null;
  max_size_bytes: number | null;
  status: RomPackStatus;
  downloaded_path: string | null;
  size_bytes: number | null;
  total_files: number;
  imported_count: number;
  unmatched_count: number;
  parked_count: number;
  failed_count: number;
  last_error: string | null;
  last_ingest_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RomPackItemRead {
  id: number;
  rom_pack_id: number;
  original_filename: string;
  extracted_path: string | null;
  size_bytes: number | null;
  crc32: string | null;
  md5: string | null;
  sha1: string | null;
  status: RomPackItemStatus;
  dat_entry_id: number | null;
  game_id: number | null;
  dump_id: number | null;
  error_msg: string | null;
  created_at: string;
  updated_at: string;
}

export interface RomPackCreate {
  name: string;
  url: string;
  platform_id?: number | null;
  max_size_bytes?: number | null;
}

export interface RomPackUpdate {
  name?: string;
  url?: string;
  platform_id?: number | null;
  max_size_bytes?: number | null;
}

const LIST_KEY = ["settings", "rom-packs"] as const;

function itemsKey(packId: number): readonly unknown[] {
  return ["settings", "rom-packs", packId, "items"] as const;
}

/** Poll every 3 s while any pack is mid-ingest, else stop. */
function _listRefetchInterval(
  query: { state: { data?: RomPackRead[] } },
): number | false {
  const data = query.state.data;
  if (data === undefined) return false;
  return data.some((p) => ROM_PACK_BUSY_STATUSES.has(p.status))
    ? 3_000
    : false;
}

export function useRomPacks(): UseQueryResult<RomPackRead[], ApiError> {
  return useQuery<RomPackRead[], ApiError>({
    queryKey: LIST_KEY,
    queryFn: () => apiFetch<RomPackRead[]>("/api/v3/rom-pack"),
    staleTime: 10_000,
    refetchInterval: _listRefetchInterval,
  });
}

export function useRomPackItems(
  packId: number,
  statusFilter?: RomPackItemStatus,
): UseQueryResult<RomPackItemRead[], ApiError> {
  const qs =
    statusFilter !== undefined
      ? `?status_filter=${encodeURIComponent(statusFilter)}`
      : "";
  return useQuery<RomPackItemRead[], ApiError>({
    queryKey: [...itemsKey(packId), statusFilter ?? "all"],
    queryFn: () =>
      apiFetch<RomPackItemRead[]>(`/api/v3/rom-pack/${packId}/items${qs}`),
    staleTime: 5_000,
  });
}

export function useCreateRomPack(): UseMutationResult<
  RomPackRead,
  ApiError,
  RomPackCreate
> {
  const qc = useQueryClient();
  return useMutation<RomPackRead, ApiError, RomPackCreate>({
    mutationFn: (payload) =>
      apiFetch<RomPackRead>("/api/v3/rom-pack", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export interface UpdateRomPackVariables {
  id: number;
  payload: RomPackUpdate;
}

export function useUpdateRomPack(): UseMutationResult<
  RomPackRead,
  ApiError,
  UpdateRomPackVariables
> {
  const qc = useQueryClient();
  return useMutation<RomPackRead, ApiError, UpdateRomPackVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<RomPackRead>(`/api/v3/rom-pack/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useDeleteRomPack(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/rom-pack/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useIngestRomPack(): UseMutationResult<
  RomPackRead,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<RomPackRead, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<RomPackRead>(`/api/v3/rom-pack/${id}/ingest`, {
        method: "POST",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}
