/**
 * Auth-related TanStack Query hooks.
 *
 * - :func:`useCurrentPrincipal` — GET /api/v3/auth/me. Powers
 *   the AuthGuard. ``staleTime: Infinity`` so the principal
 *   isn't refetched on every navigation; ``retry: false`` so
 *   the 401 surfaces immediately rather than being delayed by
 *   the default exponential backoff.
 * - :func:`useLogin` — POST /api/v3/auth/login mutation.
 *   On success invalidates the auth/me cache so the AuthGuard
 *   reads the fresh principal.
 * - :func:`useLogout` — POST /api/v3/auth/logout. Same
 *   invalidation; the next /auth/me read will 401, and
 *   AuthGuard redirects to /login.
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

export type CurrentPrincipal = components["schemas"]["UserPublic"];

export const AUTH_ME_QUERY_KEY = ["auth", "me"] as const;

export function useCurrentPrincipal(): UseQueryResult<
  CurrentPrincipal,
  ApiError
> {
  return useQuery<CurrentPrincipal, ApiError>({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: () => apiFetch<CurrentPrincipal>("/api/v3/auth/me"),
    staleTime: Infinity,
    retry: false,
  });
}

export interface LoginPayload {
  username: string;
  password: string;
}

export function useLogin(): UseMutationResult<
  void,
  ApiError,
  LoginPayload
> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, LoginPayload>({
    mutationFn: (payload) =>
      apiFetch<void>("/api/v3/auth/login", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
    },
  });
}

export interface AuthConfig {
  oidc_enabled: boolean;
  oidc_provider_label: string | null;
  oidc_start_url: string | null;
}

const AUTH_CONFIG_KEY = ["auth", "config"] as const;

/**
 * Public auth-config probe. The Login page reads this to decide
 * whether to render the "Sign in with SSO" button (spec 014 T101).
 * No authentication required — the response is the same shape
 * regardless of the operator's session.
 */
export function useAuthConfig(): UseQueryResult<AuthConfig, ApiError> {
  return useQuery<AuthConfig, ApiError>({
    queryKey: AUTH_CONFIG_KEY,
    queryFn: () => apiFetch<AuthConfig>("/api/v3/auth/config"),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useLogout(): UseMutationResult<void, ApiError, void> {
  const qc = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      apiFetch<void>("/api/v3/auth/logout", { method: "POST" }),
    onSuccess: () => {
      // Drop the principal immediately so the AuthGuard
      // redirects without a flicker.
      qc.setQueryData(AUTH_ME_QUERY_KEY, undefined);
      void qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
    },
  });
}
