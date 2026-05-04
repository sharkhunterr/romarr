/**
 * Settings > Connect (notifications) page test (spec 014 P-SET).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { ConnectPage } from "./index";
import * as notificationsQuery from "@/lib/api/queries/notifications";

const I18N_BUNDLE = {
  settings: {
    connect: {
      title: "Notifications",
      subtitle: "Apprise URLs + webhook targets.",
      empty: { title: "No notifications", body: "Configure your first one." },
      webhookDoc: { body: "Read the webhook docs.", link: "Webhook reference" },
      search: {
        label: "Search notifications",
        placeholder: "URL or label",
        noMatches: "Nothing matches.",
      },
    },
  },
};

describe("ConnectPage", () => {
  it("renders the empty-state when useNotifications returns []", () => {
    vi.spyOn(notificationsQuery, "useNotifications").mockReturnValue({
      data: [],
      isSuccess: true,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof notificationsQuery.useNotifications>);

    renderWithProviders(<ConnectPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Notifications")).toBeInTheDocument();
    expect(screen.getByText("No notifications")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Webhook reference" }),
    ).toHaveAttribute("href", "/api/v3/notification/webhook-payloads.md");
  });

  it("surfaces the API error message in the EmptyState", () => {
    vi.spyOn(notificationsQuery, "useNotifications").mockReturnValue({
      data: undefined,
      isSuccess: false,
      isLoading: false,
      isPending: false,
      isError: true,
      error: { message: "notification table missing" },
    } as unknown as ReturnType<typeof notificationsQuery.useNotifications>);

    renderWithProviders(<ConnectPage />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByText("notification table missing"),
    ).toBeInTheDocument();
  });
});
