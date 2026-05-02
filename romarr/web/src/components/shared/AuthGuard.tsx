/**
 * AuthGuard (T042, FR-006).
 *
 * Real version (slice 46): drives the auth check off
 * :func:`useCurrentPrincipal`. The TanStack Query state maps
 * to the documented contract:
 *
 *   - **isPending**: probe in flight → render the loading
 *     placeholder.
 *   - **error**: not authenticated (401) or backend
 *     unreachable → redirect to
 *     ``/login?returnTo=<encoded path>``.
 *   - **data.is_active === false**: account deactivated →
 *     render the documented "Account deactivated" surface.
 *   - **data**: render the protected ``<Outlet />``.
 *
 * The full FR-022 chain (api-key / cookie / bearer) lives in
 * the backend; the frontend just probes /auth/me with cookie
 * credentials and trusts the answer.
 */

import { type ReactElement } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useCurrentPrincipal } from "@/lib/api/queries/auth";

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

function LoadingSurface(): ReactElement {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400"
      role="status"
      aria-live="polite"
    >
      Loading…
    </div>
  );
}

function DeactivatedSurface(): ReactElement {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-50">
      <div className="w-full max-w-sm space-y-3 rounded-lg border border-amber-700/40 bg-amber-900/20 p-6 text-center">
        <h1 className="text-base font-semibold text-amber-200">
          Account deactivated
        </h1>
        <p className="text-sm text-amber-100/80">
          Contact your Romarr administrator to re-enable your
          account.
        </p>
      </div>
    </main>
  );
}

export function AuthGuard(): ReactElement {
  const { isPending, error, data } = useCurrentPrincipal();
  const location = useLocation();

  if (isPending) {
    return <LoadingSurface />;
  }

  if (error) {
    const returnTo = encodeURIComponent(
      location.pathname + location.search,
    );
    return <Navigate to={`/login?returnTo=${returnTo}`} replace />;
  }

  if (data && data.is_active === false) {
    return <DeactivatedSurface />;
  }

  return <Outlet />;
}
