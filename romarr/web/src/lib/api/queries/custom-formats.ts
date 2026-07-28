/**
 * Custom Format query / mutation hooks (slice 64).
 *
 * Wraps spec 007 / 013 /api/v3/customformat:
 *   * GET    /api/v3/customformat          (list)
 *   * GET    /api/v3/customformat/{id}     (read)
 *   * DELETE /api/v3/customformat/{id}     (admin)
 *
 * Create + update flows are deferred — the visual condition
 * builder (T097) is a meaty UX slice on its own. The MVP page
 * surfaces the read path so operators can audit the
 * factory-default catalogue and what's been customized.
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

export type CustomFormat = components["schemas"]["CustomFormatRead"];

export type CustomFormatField =
  | "title"
  | "tags"
  | "region"
  | "format"
  | "dump_status"
  | "release_group"
  | "indexer_source"
  | "languages"
  | "revision"
  | "naming_convention"
  | "release_size"
  | "info_url"
  | "nfo_url"
  | "download_url"
  | "description"
  | "indexer_guid";

export type CustomFormatOperator =
  | "matches_regex"
  | "equals"
  | "in"
  | "contains"
  | "not_in"
  | "greater_than"
  | "less_than";

export interface CustomFormatConditionInput {
  field: CustomFormatField;
  operator: CustomFormatOperator;
  values: string | number | (string | number)[];
}

export interface CustomFormatCreate {
  name: string;
  score: number;
  conditions: CustomFormatConditionInput[];
}

const CUSTOM_FORMATS_KEY = ["settings", "custom-formats"] as const;

export function useCustomFormats(): UseQueryResult<CustomFormat[], ApiError> {
  return useQuery<CustomFormat[], ApiError>({
    queryKey: CUSTOM_FORMATS_KEY,
    queryFn: () => apiFetch<CustomFormat[]>("/api/v3/customformat"),
    staleTime: 30_000,
  });
}

export function useCreateCustomFormat(): UseMutationResult<
  CustomFormat,
  ApiError,
  CustomFormatCreate
> {
  const qc = useQueryClient();
  return useMutation<CustomFormat, ApiError, CustomFormatCreate>({
    mutationFn: (payload) =>
      apiFetch<CustomFormat>("/api/v3/customformat", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CUSTOM_FORMATS_KEY });
    },
  });
}

export interface CustomFormatUpdate {
  name?: string;
  score?: number;
  conditions?: CustomFormatConditionInput[];
}

export interface UpdateCustomFormatVariables {
  id: number;
  payload: CustomFormatUpdate;
}

export function useUpdateCustomFormat(): UseMutationResult<
  CustomFormat,
  ApiError,
  UpdateCustomFormatVariables
> {
  const qc = useQueryClient();
  return useMutation<CustomFormat, ApiError, UpdateCustomFormatVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<CustomFormat>(`/api/v3/customformat/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CUSTOM_FORMATS_KEY });
    },
  });
}

export function useDeleteCustomFormat(): UseMutationResult<
  void,
  ApiError,
  number
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) =>
      apiFetch<void>(`/api/v3/customformat/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CUSTOM_FORMATS_KEY });
    },
  });
}
