/**
 * PageErrorBoundary (CL006 + CL007).
 *
 * Spec 014 FR-038a: a render-time crash inside a top-level page
 * must NOT take the shell down. The shell (header + bottom nav)
 * stays interactive; the affected page renders a localized error
 * card with:
 *
 *   * a localized title
 *   * a "Retry" action that resets the boundary so the page
 *     re-mounts (most chunk-load failures self-heal on retry)
 *   * a "Back to Dashboard" link as the safe fallback
 *   * a copyable short error id (BLAKE2-style hash of the
 *     error message + chunk name) so the operator can correlate
 *     a screenshot with backend logs
 *
 * The boundary is mounted around ``<Outlet />`` in the router
 * config; each top-level page gets its own boundary so a crash
 * on one page doesn't cascade.
 */

import {
  Component,
  type ErrorInfo,
  type ReactNode,
} from "react";

import { ErrorFallback } from "@/components/shared/ErrorFallback";

interface PageErrorBoundaryProps {
  children: ReactNode;
}

interface PageErrorBoundaryState {
  error: Error | null;
  errorId: string | null;
}

function _shortHash(input: string): string {
  // Tiny non-cryptographic hash — collision resistance is not the
  // goal, the operator just needs a stable short id to copy into
  // a bug report.
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0").slice(0, 8);
}

export class PageErrorBoundary extends Component<
  PageErrorBoundaryProps,
  PageErrorBoundaryState
> {
  state: PageErrorBoundaryState = { error: null, errorId: null };

  static getDerivedStateFromError(
    error: Error,
  ): PageErrorBoundaryState {
    const chunkName = (error as Error & { chunkName?: string })
      .chunkName;
    const seed = `${error.message ?? "error"}|${chunkName ?? ""}`;
    return { error, errorId: _shortHash(seed) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console-only — FR-038b prohibits remote error reporting.
    // eslint-disable-next-line no-console
    console.error(
      "[PageErrorBoundary]",
      error.message,
      info.componentStack,
    );
  }

  reset = (): void => {
    this.setState({ error: null, errorId: null });
  };

  render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <ErrorFallback
          error={this.state.error}
          errorId={this.state.errorId ?? "unknown"}
          onRetry={this.reset}
        />
      );
    }
    return this.props.children;
  }
}
