/**
 * App-level :class:`QueryClientProvider` wrapper.
 *
 * Single shared client for the whole SPA — TanStack Query
 * caches the responses across pages so navigating
 * Library → Game Detail → Library hits the cache instead
 * of refetching. Defaults are tuned for Romarr's read-heavy
 * surface:
 *
 *   * ``staleTime: 30s`` — most lists tolerate a 30-second
 *     stale window without confusing the operator.
 *   * ``refetchOnWindowFocus: false`` — Romarr is a long-
 *     dwell ops UI; the operator coming back to a tab
 *     doesn't want every list to refetch.
 *   * ``retry: 1`` — the auth-tier surface (401) MUST NOT
 *     retry; per-query overrides handle that
 *     (see ``useCurrentPrincipal``).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactElement, type ReactNode } from "react";

export interface QueryProviderProps {
  children: ReactNode;
}

function buildClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}

export function QueryProvider(
  props: QueryProviderProps,
): ReactElement {
  // ``useState`` so the client survives Strict-Mode double-mounts
  // without being re-instantiated.
  const [client] = useState(() => buildClient());
  return (
    <QueryClientProvider client={client}>
      {props.children}
    </QueryClientProvider>
  );
}
