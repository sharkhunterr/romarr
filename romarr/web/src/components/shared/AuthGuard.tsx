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
 *
 * Strings resolve through `common:guard.*` (slice 70).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useCurrentPrincipal } from "@/lib/api/queries/auth";

function LoadingSurface(): ReactElement {
  const { t } = useTranslation("common");
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400"
      role="status"
      aria-live="polite"
    >
      {t("guard.loading")}
    </div>
  );
}

function DeactivatedSurface(): ReactElement {
  const { t } = useTranslation("common");
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-50">
      <div className="w-full max-w-sm space-y-3 rounded-lg border border-amber-700/40 bg-amber-900/20 p-6 text-center">
        <h1 className="text-base font-semibold text-amber-200">
          {t("guard.deactivatedTitle")}
        </h1>
        <p className="text-sm text-amber-100/80">
          {t("guard.deactivatedBody")}
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
