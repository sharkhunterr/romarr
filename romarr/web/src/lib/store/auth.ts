/**
 * Auth state store.
 *
 * The full integration (TanStack Query against
 * ``GET /api/v3/auth/me``) lands when the query runtime
 * dependency arrives. Today's store is a small zustand state
 * holder: ``status: "loading" | "authed" | "unauthed"`` plus
 * the resolved principal when authenticated. The AuthGuard
 * reads this; the login page writes it.
 *
 * The default ``status: "unauthed"`` means the AuthGuard
 * redirects to ``/login`` immediately on first paint until the
 * /api/v3/auth/me probe lands. That matches the spec
 * "protected route + unauthenticated state redirects to /login"
 * contract (T038).
 */

import { create } from "zustand";

export interface AuthPrincipal {
  username: string;
  role: "admin" | "user" | "readonly";
  isActive: boolean;
}

export type AuthStatus = "loading" | "authed" | "unauthed";

interface AuthState {
  status: AuthStatus;
  principal: AuthPrincipal | null;
  setAuthed: (principal: AuthPrincipal) => void;
  setUnauthed: () => void;
  setLoading: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: "unauthed",
  principal: null,
  setAuthed: (principal) => set({ status: "authed", principal }),
  setUnauthed: () => set({ status: "unauthed", principal: null }),
  setLoading: () => set({ status: "loading" }),
}));
