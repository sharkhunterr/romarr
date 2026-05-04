/**
 * System page test (spec 014 P-SYS).
 *
 * The page picks one of four tabs from the URL `:sub`
 * param. Without `<Routes>` `useParams()` returns `{}`, so
 * the default is the Status tab. We mock useSystemStatus
 * (StatusTab) plus the queries every other tab might fire
 * if the user clicks through.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { SystemPage } from "./index";
import * as systemQuery from "@/lib/api/queries/system";

const I18N_BUNDLE = {
  system: {
    title: "System",
    subtitle: "Runtime + scheduled jobs.",
    tabs: {
      ariaLabel: "System tabs",
      status: "Status",
      tasks: "Tasks",
      logs: "Logs",
      backup: "Backup",
    },
    status: {
      version: "Version",
      instanceName: "Instance",
      runtimeVersion: "Runtime",
      runtimeName: "Runtime name",
      osName: "OS",
      databaseType: "Database",
      databaseVersion: "Database version",
      migrationVersion: "Migration",
      startTime: "Started at",
      appData: "App data",
      isProduction: "Production",
      urlBase: "URL base",
      empty: "No status data",
      loadError: "Status query failed",
      loading: "Loading…",
      dash: "—",
    },
  },
};

describe("SystemPage", () => {
  it("renders the title + the four documented tab buttons", () => {
    vi.spyOn(systemQuery, "useSystemStatus").mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof systemQuery.useSystemStatus>);

    renderWithProviders(<SystemPage />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByRole("heading", { name: "System" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Status" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Backup" })).toBeInTheDocument();
  });

  it("surfaces the system version + instanceName under the Status tab", () => {
    vi.spyOn(systemQuery, "useSystemStatus").mockReturnValue({
      data: {
        version: "0.14.0",
        isProduction: true,
        instanceName: "Romarr-prod",
        runtimeVersion: "3.12.6",
        runtimeName: "CPython",
        databaseType: "sqlite",
        osName: "linux",
      },
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof systemQuery.useSystemStatus>);

    renderWithProviders(<SystemPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("0.14.0")).toBeInTheDocument();
    expect(screen.getByText("Romarr-prod")).toBeInTheDocument();
    expect(screen.getByText("3.12.6")).toBeInTheDocument();
  });
});
