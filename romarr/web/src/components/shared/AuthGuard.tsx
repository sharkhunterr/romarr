/**
 * AuthGuard (T042, FR-006).
 *
 * Protected-route wrapper. Reads the auth status from the
 * zustand store; on ``unauthed`` redirects to
 * ``/login?returnTo=<current path>``. On ``loading`` renders
 * a minimal placeholder so the user sees something during the
 * /api/v3/auth/me round-trip (lands with the TanStack Query
 * integration). On ``authed`` renders the protected outlet.
 *
 * The full ``is_active=false`` "Account deactivated" surface
 * lands once the principal carries the flag (T042 stretch).
 */

import { type ReactElement } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthStore } from "@/lib/store/auth";

export function AuthGuard(): ReactElement {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();

  if (status === "loading") {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400"
        role="status"
        aria-live="polite"
      >
        {/* eslint-disable-next-line react/jsx-no-literals */}
        Loading…
      </div>
    );
  }

  if (status === "unauthed") {
    const returnTo = encodeURIComponent(
      location.pathname + location.search,
    );
    return <Navigate to={`/login?returnTo=${returnTo}`} replace />;
  }

  return <Outlet />;
}
