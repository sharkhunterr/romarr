/**
 * Login page tests (spec 014 T100, T101).
 *
 * Mocks the ``useLogin`` mutation so the form's success +
 * error paths render deterministically.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { LoginPage } from "./index";
import * as authQuery from "@/lib/api/queries/auth";
import { ApiError } from "@/lib/api/client";

const I18N_BUNDLE = {
  auth: {
    setupLink: "Run setup wizard",
    login: {
      title: "Sign in",
      username: "Username",
      password: "Password",
      submit: "Sign in",
      submitting: "Signing in…",
      setupHint: "First time?",
      returnToHint: "Will return to {{path}}",
      errors: {
        unauthenticated: "Wrong username or password",
        rate_limited: "Too many attempts; wait a minute",
        fallback: "Something went wrong, try again",
      },
    },
  },
};


function _mockLogin(
  overrides: Partial<ReturnType<typeof authQuery.useLogin>>,
): void {
  vi.spyOn(authQuery, "useLogin").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof authQuery.useLogin>);
}

interface AuthConfigStub {
  oidc_enabled: boolean;
  oidc_provider_label?: string | null;
  oidc_start_url?: string | null;
}

function _mockAuthConfig(stub: AuthConfigStub): void {
  vi.spyOn(authQuery, "useAuthConfig").mockReturnValue({
    data: {
      oidc_enabled: stub.oidc_enabled,
      oidc_provider_label: stub.oidc_provider_label ?? null,
      oidc_start_url: stub.oidc_start_url ?? null,
    },
    isSuccess: true,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof authQuery.useAuthConfig>);
}

describe("LoginPage", () => {
  it("renders the username + password form with the documented labels", () => {
    _mockLogin({});
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("disables the submit button + shows submitting copy while pending", () => {
    _mockLogin({ isPending: true });
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    const button = screen.getByRole("button", { name: "Signing in…" });
    expect(button).toBeDisabled();
  });

  it("calls login.mutate with the typed username + password", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    _mockLogin({ mutate });
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "horse battery staple");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0]?.[0]).toEqual({
      username: "alice",
      password: "horse battery staple",
    });
  });

  it("renders the unauthenticated error message on 401", () => {
    _mockLogin({
      error: new ApiError(401, {
        errorMessage: "unauthenticated",
        errorCode: "unauthenticated",
      }),
    });
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Wrong username or password",
    );
  });

  it("renders the rate-limit error on 429", () => {
    _mockLogin({
      error: new ApiError(429, {
        errorMessage: "rate_limited",
        errorCode: "rate_limited",
      }),
    });
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Too many attempts; wait a minute",
    );
  });

  it("links to the setup wizard for first-boot operators", () => {
    _mockLogin({});
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    const setupLink = screen.getByRole("link", { name: "Run setup wizard" });
    expect(setupLink).toBeInTheDocument();
    expect(setupLink.getAttribute("href")).toBe("/setup");
  });

  it("does NOT render the SSO button when oidc_enabled=false (T101)", () => {
    _mockLogin({});
    _mockAuthConfig({ oidc_enabled: false });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    // No element labelled "Sign in with ..." beyond the Forms
    // submit button.
    expect(
      screen.queryByRole("link", { name: /Sign in with/ }),
    ).toBeNull();
  });

  it("renders the SSO button + start_url when oidc_enabled (T101)", () => {
    _mockLogin({});
    _mockAuthConfig({
      oidc_enabled: true,
      oidc_provider_label: "Authentik",
      oidc_start_url: "/api/v3/auth/oidc/start",
    });

    renderWithProviders(
      <LoginPage />,
      {
        i18nResources: {
          auth: {
            ...I18N_BUNDLE.auth,
            login: {
              ...I18N_BUNDLE.auth.login,
              ssoButton: "Sign in with {{provider}}",
              ssoFallback: "SSO",
            },
          },
        },
      },
    );

    const sso = screen.getByRole("link", { name: "Sign in with Authentik" });
    expect(sso).toBeInTheDocument();
    expect(sso.getAttribute("href")).toBe("/api/v3/auth/oidc/start");
  });
});
