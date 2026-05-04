/**
 * AuthGuard test (spec 014 T038).
 *
 * Four documented branches: isPending → loading surface;
 * error → Navigate to /login?returnTo=…; data with
 * is_active=false → deactivated surface; data with
 * is_active=true → child Outlet renders.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "@/test/render";

import { AuthGuard } from "./AuthGuard";
import * as authQuery from "@/lib/api/queries/auth";

const I18N_BUNDLE = {
  common: {
    guard: {
      loading: "Loading…",
      deactivatedTitle: "Account deactivated",
      deactivatedBody: "Reach out to an administrator.",
    },
  },
};

function _renderWithGuard(initialPath: string): void {
  renderWithProviders(
    <Routes>
      <Route element={<AuthGuard />}>
        <Route path="/library" element={<p>Protected content</p>} />
      </Route>
      <Route path="/login" element={<p>Login page</p>} />
    </Routes>,
    {
      i18nResources: I18N_BUNDLE,
      routerEntries: [initialPath],
    },
  );
}

describe("AuthGuard", () => {
  it("renders the loading surface while the principal probe is in flight", () => {
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      isPending: true,
      error: null,
      data: undefined,
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);

    _renderWithGuard("/library");

    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(screen.queryByText("Protected content")).toBeNull();
  });

  it("redirects to /login?returnTo=… when the principal probe errors", () => {
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      isPending: false,
      error: new Error("401"),
      data: undefined,
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);

    _renderWithGuard("/library");

    // After the redirect MemoryRouter renders the /login route's
    // element. The returnTo query param carries the original
    // path so the post-login redirect can return the operator.
    expect(screen.getByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).toBeNull();
  });

  it("renders the deactivated surface when data.is_active is false", () => {
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      isPending: false,
      error: null,
      data: { kind: "user", role: "user", username: "alice", is_active: false },
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);

    _renderWithGuard("/library");

    expect(screen.getByText("Account deactivated")).toBeInTheDocument();
    expect(
      screen.getByText("Reach out to an administrator."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).toBeNull();
  });

  it("renders the protected child Outlet when the operator is authenticated and active", () => {
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      isPending: false,
      error: null,
      data: { kind: "user", role: "user", username: "alice", is_active: true },
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);

    _renderWithGuard("/library");

    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});
