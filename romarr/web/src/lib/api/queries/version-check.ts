/**
 * Version check hook — polls the running Romarr against the latest
 * GitHub release. Backend caches for 1 h, this hook adds a 30 min
 * ``staleTime`` so a mobile that opens Settings twice in a minute
 * doesn't refetch. Pass ``force`` on the "Check now" mutation to
 * bypass both caches.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";

export interface VersionCheck {
  current: string;
  latest: string | null;
  updateAvailable: boolean;
  releaseUrl: string | null;
  publishedAt: string | null;
  error: string | null;
  repo: string;
}

const KEY = ["system", "version-check"] as const;

export function useVersionCheck(): UseQueryResult<VersionCheck, ApiError> {
  return useQuery<VersionCheck, ApiError>({
    queryKey: KEY,
    queryFn: () =>
      apiFetch<VersionCheck>("/api/v3/system/version-check"),
    staleTime: 30 * 60_000,
  });
}

export function useForceVersionCheck(): UseMutationResult<
  VersionCheck,
  ApiError,
  void
> {
  const qc = useQueryClient();
  return useMutation<VersionCheck, ApiError, void>({
    mutationFn: () =>
      apiFetch<VersionCheck>("/api/v3/system/version-check?force=true"),
    onSuccess: (data) => {
      qc.setQueryData(KEY, data);
      // Update Center popover reads from the aggregated feed, which
      // pulls its Romarr half from the same backend cache. Force
      // refresh means we want the badge in sync — invalidate the
      // feed so it re-fetches.
      void qc.invalidateQueries({ queryKey: ["community", "updates"] });
    },
  });
}
