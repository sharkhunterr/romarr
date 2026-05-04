/**
 * Dashboard page test (spec 014 T091).
 *
 * The page composes four sub-components — HealthPanel,
 * PlatformBreakdown, ActivityFeed, QuickActions — each of
 * which fires its own query. Mocks here cover every read-side
 * hook the page touches; useTriggerCommand stays real because
 * its mutation only fires on click.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { DashboardPage } from "./index";
import * as systemQuery from "@/lib/api/queries/system";

const I18N_BUNDLE = {
  dashboard: {
    title: "Dashboard",
    subtitle: "At-a-glance system health.",
    sections: {
      library: "Library",
      platformBreakdown: "Platform breakdown",
      quickActions: "Quick actions",
      recentActivity: "Recent activity",
    },
    stats: {
      version: "Version",
      instance: "Instance",
      uptime: "Uptime",
      runtime: "Runtime",
      uptimeDash: "—",
      uptimeHint: "since boot",
      uptimeSeconds_one: "{{count}} second",
      uptimeSeconds_other: "{{count}} seconds",
      uptimeMinutes_one: "{{count}} minute",
      uptimeMinutes_other: "{{count}} minutes",
      uptimeHours: "{{hours}}h {{minutes}}m",
      uptimeDays: "{{days}}d {{hours}}h",
    },
    library: {
      totalGames: "Games",
      totalReleases: "Releases",
      totalDumps: "Dumps",
      imports24h: "Imports 24h",
      monitoredHint: "{{count}} monitored",
      wantedHint: "{{count}} wanted",
      totalDumpsHint: "verified files",
      importsSuccessHint: "{{count}} OK",
    },
    health: {
      empty: "All checks passing",
      loadError: "Health snapshot unavailable",
    },
    platform: {
      empty: "No platforms scanned yet",
      loadError: "Platform stats unavailable",
    },
    activity: {
      empty: { title: "No recent activity", body: "Logs will land here." },
      loadError: "History unavailable",
    },
    quick: {
      missingSearch: "Trigger missing search",
      backup: "Run backup",
      openWanted: "Open Wanted",
    },
  },
};

function _baseStatus(): ReturnType<typeof systemQuery.useSystemStatus> {
  return {
    data: {
      version: "0.14.0",
      isProduction: true,
      instanceName: "Romarr-prod",
      runtimeName: "CPython",
      runtimeVersion: "3.12.6",
      databaseType: "sqlite",
      osName: "linux",
      startTime: new Date(Date.now() - 60 * 1000).toISOString(),
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof systemQuery.useSystemStatus>;
}

function _baseStats(): ReturnType<typeof systemQuery.useSystemStats> {
  return {
    data: {
      totalGames: 42,
      totalReleases: 128,
      totalDumps: 30,
      monitoredGames: 12,
      wantedReleases: 8,
      imports24h: 5,
      importsSuccess24h: 4,
      byPlatform: [],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof systemQuery.useSystemStats>;
}

function _emptyHealth(): ReturnType<typeof systemQuery.useHealth> {
  return {
    data: { status: "ok", entries: [] },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof systemQuery.useHealth>;
}

function _emptyHistory(): ReturnType<typeof systemQuery.useHistory> {
  return {
    data: {
      page: 1,
      pageSize: 50,
      sortKey: "date",
      sortDirection: "desc",
      totalRecords: 0,
      records: [],
    },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof systemQuery.useHistory>;
}

function _stubAll(): void {
  vi.spyOn(systemQuery, "useSystemStatus").mockReturnValue(_baseStatus());
  vi.spyOn(systemQuery, "useSystemStats").mockReturnValue(_baseStats());
  vi.spyOn(systemQuery, "useHealth").mockReturnValue(_emptyHealth());
  vi.spyOn(systemQuery, "useHistory").mockReturnValue(_emptyHistory());
}

describe("DashboardPage", () => {
  it("renders the title, subtitle, and the four documented sections", () => {
    _stubAll();

    renderWithProviders(<DashboardPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("At-a-glance system health.")).toBeInTheDocument();
    expect(screen.getByText("Library")).toBeInTheDocument();
    expect(screen.getByText("Platform breakdown")).toBeInTheDocument();
    expect(screen.getByText("Quick actions")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
  });

  it("surfaces system-status fields in the four status cards", () => {
    _stubAll();

    renderWithProviders(<DashboardPage />, { i18nResources: I18N_BUNDLE });

    // version + instanceName + runtimeVersion all surface as
    // StatCard values (the uptime card depends on Date.now,
    // which we don't pin here — covered by the formatter unit
    // tests).
    expect(screen.getByText("0.14.0")).toBeInTheDocument();
    expect(screen.getByText("Romarr-prod")).toBeInTheDocument();
    expect(screen.getByText("3.12.6")).toBeInTheDocument();
  });

  it("surfaces aggregate counts from useSystemStats", () => {
    _stubAll();

    renderWithProviders(<DashboardPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("falls back to the version-dash placeholder when status query is loading", () => {
    vi.spyOn(systemQuery, "useSystemStatus").mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof systemQuery.useSystemStatus>);
    vi.spyOn(systemQuery, "useSystemStats").mockReturnValue(_baseStats());
    vi.spyOn(systemQuery, "useHealth").mockReturnValue(_emptyHealth());
    vi.spyOn(systemQuery, "useHistory").mockReturnValue(_emptyHistory());

    renderWithProviders(<DashboardPage />, { i18nResources: I18N_BUNDLE });

    // Header still shows; status cards render skeletons (no
    // version text yet, but "Romarr" instance fallback shows).
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("0.14.0")).toBeNull();
  });
});
