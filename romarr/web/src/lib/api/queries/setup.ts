/**
 * First-boot setup mutation (T109, P-SETUP).
 *
 * Wraps POST /api/v3/auth/setup (spec 011 + 013) — consumes the
 * `X-Setup-Token` from the operator and creates the first
 * admin user. Per FR-020 the call is atomic: success returns
 * the new admin AND sets the session cookie, so the operator
 * is logged in immediately.
 *
 * The token comes from the server logs on first boot
 * (printed once); the operator pastes it into the wizard
 * which forwards it as the `X-Setup-Token` header. Wrong /
 * expired tokens surface as ApiError with errorCode
 * `setup_token_invalid`.
 */

import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import { AUTH_ME_QUERY_KEY } from "@/lib/api/queries/auth";
import type { components } from "@/types/api/schema";

export type SetupRequest = components["schemas"]["SetupRequest"];
export type SetupResponse = components["schemas"]["SetupResponse"];

export interface SetupVariables {
  /** From the server boot logs. */
  token: string;
  username: string;
  password: string;
}

export function useSetup(): UseMutationResult<
  SetupResponse,
  ApiError,
  SetupVariables
> {
  const qc = useQueryClient();
  return useMutation<SetupResponse, ApiError, SetupVariables>({
    mutationFn: ({ token, username, password }) =>
      apiFetch<SetupResponse>("/api/v3/auth/setup", {
        method: "POST",
        json: { username, password } satisfies SetupRequest,
        headers: { "X-Setup-Token": token },
      }),
    onSuccess: () => {
      // Setup logs the operator in atomically (FR-020); refresh
      // the principal probe so the SPA sees the new session.
      void qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
    },
  });
}
