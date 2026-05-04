/**
 * Settings > General page test (spec 014 P-SET).
 *
 * Mocks every read-side hook the page touches plus the
 * create-form mutations. The admin section gates on the
 * principal's role; we cover both the operator (no admin
 * section) and the admin (with users panel) paths.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { GeneralPage } from "./index";
import * as apiKeysQuery from "@/lib/api/queries/api-keys";
import * as authQuery from "@/lib/api/queries/auth";
import * as usersQuery from "@/lib/api/queries/users";

const I18N_BUNDLE = {
  settings: {
    general: {
      title: "General",
      subtitle: "Per-user API keys + admin operator panel.",
      apiKeys: {
        section: "API keys",
        empty: {
          title: "No API keys",
          body: "Mint your first key for tooling integration.",
        },
        create: {
          title: "Mint API key",
          nameLabel: "Name",
          namePlaceholder: "ci-bot",
          scopesLabel: "Scopes",
          scopesPlaceholder: "read,write",
          scopesHint: "Comma-separated; * for unrestricted.",
          submit: "Mint key",
          pending: "Minting…",
        },
        created: {
          title: "Key created",
          body: "Copy the plaintext for {{name}} once — we won't show it again.",
          copy: "Copy",
        },
      },
      users: {
        section: "Operators",
        adminOnly: "admin",
        subtitle: "Add or remove operator accounts.",
        empty: {
          title: "No operators yet",
          body: "Invite a teammate to share the load.",
        },
        create: {
          title: "Add operator",
          usernameLabel: "Username",
          usernamePlaceholder: "alice",
          passwordLabel: "Password",
          passwordPlaceholder: "≥8 chars",
          roleLabel: "Role",
          submit: "Create operator",
          pending: "Creating…",
        },
      },
    },
  },
};

function _baseStubs(): void {
  vi.spyOn(apiKeysQuery, "useCreateApiKey").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    data: undefined,
    error: null,
  } as unknown as ReturnType<typeof apiKeysQuery.useCreateApiKey>);
  vi.spyOn(usersQuery, "useCreateUser").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof usersQuery.useCreateUser>);
  vi.spyOn(usersQuery, "useUsers").mockReturnValue({
    data: [],
    isSuccess: true,
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof usersQuery.useUsers>);
}

describe("GeneralPage", () => {
  it("renders the API-keys section with empty-state for non-admin operators", () => {
    vi.spyOn(apiKeysQuery, "useApiKeys").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof apiKeysQuery.useApiKeys>);
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      data: { kind: "user", role: "user", username: "bob" },
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);
    _baseStubs();

    renderWithProviders(<GeneralPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("API keys")).toBeInTheDocument();
    expect(screen.getByText("No API keys")).toBeInTheDocument();
    // Non-admin → Operators section MUST NOT render.
    expect(screen.queryByText("Operators")).toBeNull();
  });

  it("renders the admin Operators section when the principal is admin", () => {
    vi.spyOn(apiKeysQuery, "useApiKeys").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof apiKeysQuery.useApiKeys>);
    vi.spyOn(authQuery, "useCurrentPrincipal").mockReturnValue({
      data: { kind: "user", role: "admin", username: "alice" },
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authQuery.useCurrentPrincipal>);
    _baseStubs();

    renderWithProviders(<GeneralPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Operators")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
  });
});
