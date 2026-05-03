/**
 * Tag CRUD TanStack Query hooks.
 *
 * Wraps the spec 013 /api/v3/tag* surface (slice 24): list +
 * read + create + update + delete + polymorphic detail. Mirrors
 * the spec 013 Q5 clarification — tags are global with a
 * polymorphic association table.
 */

import { useMemo } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/types/api/schema";

export type Tag = components["schemas"]["TagRead"];
export type CreateTagRequest = components["schemas"]["CreateTagRequest"];
export type UpdateTagRequest = components["schemas"]["UpdateTagRequest"];
export type TagDetail = components["schemas"]["TagDetail"];

const TAGS_KEY = ["tags"] as const;

export function useTags(): UseQueryResult<Tag[], ApiError> {
  return useQuery<Tag[], ApiError>({
    queryKey: TAGS_KEY,
    queryFn: () => apiFetch<Tag[]>("/api/v3/tag"),
    staleTime: 60_000,
  });
}

/**
 * Lookup helper — id → Tag. Returns an empty Map until the
 * underlying query resolves. Memoised so consumers don't
 * rebuild the index every render. Drives the per-row tag-dot
 * rendering on Library cards (slice 137).
 */
export function useTagsById(): Map<number, Tag> {
  const tags = useTags();
  return useMemo(() => {
    const out = new Map<number, Tag>();
    for (const tag of tags.data ?? []) {
      out.set(tag.id, tag);
    }
    return out;
  }, [tags.data]);
}

export function useTagDetail(
  tagId: number | null,
): UseQueryResult<TagDetail, ApiError> {
  return useQuery<TagDetail, ApiError>({
    queryKey: ["tags", "detail", tagId],
    queryFn: () => apiFetch<TagDetail>(`/api/v3/tag/detail/${tagId}`),
    enabled: tagId !== null,
    staleTime: 30_000,
  });
}

export function useCreateTag(): UseMutationResult<
  Tag,
  ApiError,
  CreateTagRequest
> {
  const qc = useQueryClient();
  return useMutation<Tag, ApiError, CreateTagRequest>({
    mutationFn: (payload) =>
      apiFetch<Tag>("/api/v3/tag", { method: "POST", json: payload }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TAGS_KEY });
    },
  });
}

export interface UpdateTagVariables {
  id: number;
  payload: UpdateTagRequest;
}

export function useUpdateTag(): UseMutationResult<
  Tag,
  ApiError,
  UpdateTagVariables
> {
  const qc = useQueryClient();
  return useMutation<Tag, ApiError, UpdateTagVariables>({
    mutationFn: ({ id, payload }) =>
      apiFetch<Tag>(`/api/v3/tag/${id}`, {
        method: "PUT",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TAGS_KEY });
    },
  });
}

export interface DeleteTagVariables {
  id: number;
  /**
   * Cascade-delete the tag_assignment rows when the tag is in
   * use. Default is false, which matches the spec 013 contract
   * — DELETE returns 409 with errorCode "tag_in_use" when the
   * tag has assignments and ?force=true isn't supplied.
   */
  force?: boolean;
}

export function useDeleteTag(): UseMutationResult<
  void,
  ApiError,
  DeleteTagVariables
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, DeleteTagVariables>({
    mutationFn: ({ id, force }) =>
      apiFetch<void>(
        `/api/v3/tag/${id}${force ? "?force=true" : ""}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TAGS_KEY });
    },
  });
}
