/**
 * Setup wizard tests (spec 014 T102, T103).
 *
 * Three-step flow: Welcome → Admin → Done. Each test exercises
 * either the navigation between steps or the mutation paths
 * within the Admin step.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { SetupPage } from "./index";
import * as setupQuery from "@/lib/api/queries/setup";
import { ApiError } from "@/lib/api/client";

const I18N_BUNDLE = {
  setup: {
    title: "Romarr setup",
    next: "Next",
    back: "Back",
    stepLabel: "Step {{current}} of {{total}}",
    welcome: {
      heading: "Welcome",
      body: "Let's get you started.",
      tokenHint: "Capture the setup token from your container logs.",
    },
    admin: {
      heading: "Create the admin user",
      body: "Paste the token and pick credentials.",
      token: "Setup token",
      tokenPlaceholder: "Paste here",
      username: "Username",
      password: "Password",
      passwordHelp: "Minimum 8 characters.",
      submit: "Create admin",
      submitting: "Creating…",
    },
    done: {
      heading: "All set",
      body: "You're logged in.",
      openDashboard: "Open dashboard",
      configureLater: "Configure later",
      configureMediaManagement: "Libraries",
      configureIndexers: "Indexers",
      configureDownloadClients: "Download clients",
    },
    errors: {
      setupTokenInvalid: "Wrong token",
      setupAlreadyDone: "Setup already complete",
      validation: "Check the form fields",
      fallback: "Try again",
    },
  },
};


function _mockSetup(
  overrides: Partial<ReturnType<typeof setupQuery.useSetup>>,
): ReturnType<typeof vi.fn> {
  const mutate = vi.fn();
  vi.spyOn(setupQuery, "useSetup").mockReturnValue({
    mutate,
    isPending: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof setupQuery.useSetup>);
  return mutate;
}

describe("SetupPage", () => {
  it("renders the Welcome step on first render with the documented labels", () => {
    _mockSetup({});

    renderWithProviders(<SetupPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Welcome")).toBeInTheDocument();
    expect(
      screen.getByText("Let's get you started."),
    ).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
  });

  it("transitions to the Admin step when Next is clicked", async () => {
    _mockSetup({});
    const user = userEvent.setup();

    renderWithProviders(<SetupPage />, { i18nResources: I18N_BUNDLE });

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      screen.getByText("Create the admin user"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Setup token")).toBeInTheDocument();
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
  });

  it("calls setup.mutate with trimmed token + credentials on submit", async () => {
    const mutate = _mockSetup({});
    const user = userEvent.setup();

    renderWithProviders(<SetupPage />, { i18nResources: I18N_BUNDLE });
    await user.click(screen.getByRole("button", { name: "Next" }));

    await user.type(screen.getByLabelText("Setup token"), "  TOK-123  ");
    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(
      screen.getByLabelText("Password"),
      "horse-battery-staple",
    );
    await user.click(screen.getByRole("button", { name: "Create admin" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      token: "TOK-123",
      username: "admin",
      password: "horse-battery-staple",
    });
  });

  it("renders the wrong-token error when the mutation returns 401", async () => {
    _mockSetup({
      error: new ApiError(401, {
        errorMessage: "setup_token_invalid",
        errorCode: "setup_token_invalid",
      }),
    });
    const user = userEvent.setup();

    renderWithProviders(<SetupPage />, { i18nResources: I18N_BUNDLE });
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Wrong token");
  });

  it("disables Create + shows submitting copy while pending", async () => {
    _mockSetup({ isPending: true });
    const user = userEvent.setup();

    renderWithProviders(<SetupPage />, { i18nResources: I18N_BUNDLE });
    await user.click(screen.getByRole("button", { name: "Next" }));

    const submit = screen.getByRole("button", { name: "Creating…" });
    expect(submit).toBeDisabled();
  });
});
