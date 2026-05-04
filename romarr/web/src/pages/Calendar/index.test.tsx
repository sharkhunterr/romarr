/**
 * Calendar page test (spec 014 T094).
 *
 * Mocks the ``useCalendar`` query hook so the page renders
 * deterministically without hitting the network. Covers the
 * three documented states: loading, empty, populated.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { CalendarPage } from "./index";
import * as calendarQuery from "@/lib/api/queries/calendar";

const I18N_BUNDLE = {
  calendar: {
    title: "Calendar",
    subtitle: "Upcoming preservation events",
    loadError: "Failed to load calendar",
    nav: {
      previous: "Previous month",
      next: "Next month",
      today: "Today",
    },
    empty: {
      title: "No events scheduled",
      body: "Configure a preservation calendar source.",
    },
    monitoredAria: "Monitored",
    kind: { release: "Release" },
  },
};

describe("CalendarPage", () => {
  it("renders the loading skeleton while the query is pending", () => {
    vi.spyOn(calendarQuery, "useCalendar").mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
    } as ReturnType<typeof calendarQuery.useCalendar>);

    renderWithProviders(<CalendarPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Calendar")).toBeInTheDocument();
    // ListSkeleton from LoadingSkeleton renders aria-hidden divs;
    // we just confirm no error/empty banner shows.
    expect(screen.queryByText("No events scheduled")).toBeNull();
    expect(screen.queryByText("Failed to load calendar")).toBeNull();
  });

  it("renders the documented empty-state when the query returns []", () => {
    vi.spyOn(calendarQuery, "useCalendar").mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [],
    } as ReturnType<typeof calendarQuery.useCalendar>);

    renderWithProviders(<CalendarPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("No events scheduled")).toBeInTheDocument();
    expect(
      screen.getByText("Configure a preservation calendar source."),
    ).toBeInTheDocument();
  });

  it("renders the error banner when the query fails", () => {
    vi.spyOn(calendarQuery, "useCalendar").mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      error: new Error("boom"),
    } as ReturnType<typeof calendarQuery.useCalendar>);

    renderWithProviders(<CalendarPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Failed to load calendar")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders one card per event when the query returns data", () => {
    vi.spyOn(calendarQuery, "useCalendar").mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [
        {
          id: 1,
          title: "Sonic 1 fan-translation",
          releaseDate: "2026-06-01",
          kind: "release",
          monitored: true,
          summary: "Spanish translation patch.",
        },
        {
          id: 2,
          title: "Streets of Rage 2 hack",
          releaseDate: "2026-06-15",
          kind: "release",
          monitored: false,
        },
      ],
    } as ReturnType<typeof calendarQuery.useCalendar>);

    renderWithProviders(<CalendarPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Sonic 1 fan-translation")).toBeInTheDocument();
    expect(
      screen.getByText("Streets of Rage 2 hack"),
    ).toBeInTheDocument();
    // Monitored star only on the first event.
    expect(screen.getAllByLabelText("Monitored").length).toBe(1);
  });
});
