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

describe("LoginPage", () => {
  it("renders the username + password form with the documented labels", () => {
    _mockLogin({});

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("disables the submit button + shows submitting copy while pending", () => {
    _mockLogin({ isPending: true });

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    const button = screen.getByRole("button", { name: "Signing in…" });
    expect(button).toBeDisabled();
  });

  it("calls login.mutate with the typed username + password", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    _mockLogin({ mutate });

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

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Too many attempts; wait a minute",
    );
  });

  it("links to the setup wizard for first-boot operators", () => {
    _mockLogin({});

    renderWithProviders(<LoginPage />, { i18nResources: I18N_BUNDLE });

    const setupLink = screen.getByRole("link", { name: "Run setup wizard" });
    expect(setupLink).toBeInTheDocument();
    expect(setupLink.getAttribute("href")).toBe("/setup");
  });
});
