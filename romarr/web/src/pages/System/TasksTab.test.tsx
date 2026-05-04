/**
 * TasksTab tests (spec 014 T099 follow-up).
 *
 * Verifies the TasksTab's documented contract:
 *   * Empty list → empty-state copy.
 *   * Populated list → one row per Job, each surfacing the
 *     job id and last-run status badge.
 *   * Disabled jobs hide the "Run now" trigger button.
 *   * "Run now" button fires useTriggerCommand.mutate with
 *     ``name: job.id``.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { TasksTab } from "./TasksTab";
import * as systemQuery from "@/lib/api/queries/system";
import * as systemExtras from "@/lib/api/queries/system-extras";

const I18N_BUNDLE = {
  system: {
    tasks: {
      empty: { title: "No scheduled jobs", body: "Configure a schedule." },
      loadError: "Tasks unavailable",
      schedule: {
        cron: "{{value}}",
        intervalSeconds_one: "every {{count}}s",
        intervalSeconds_other: "every {{count}}s",
        intervalMinutes_one: "every {{count}}m",
        intervalMinutes_other: "every {{count}}m",
        intervalHours_one: "every {{count}}h",
        intervalHours_other: "every {{count}}h",
        eventDriven: "event-driven",
      },
      lastNext: "Last: {{last}} · Next: {{next}}",
      dash: "—",
      trigger: "Run now",
      triggering: "Running…",
    },
  },
};

function _stubTrigger(): ReturnType<typeof vi.fn> {
  const mutate = vi.fn();
  vi.spyOn(systemQuery, "useTriggerCommand").mockReturnValue({
    mutate,
    isPending: false,
    variables: undefined,
  } as unknown as ReturnType<typeof systemQuery.useTriggerCommand>);
  return mutate;
}

describe("TasksTab", () => {
  it("renders the empty-state when useTasks returns []", () => {
    vi.spyOn(systemExtras, "useTasks").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof systemExtras.useTasks>);
    _stubTrigger();

    renderWithProviders(<TasksTab />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("No scheduled jobs")).toBeInTheDocument();
  });

  it("surfaces the API error when useTasks fails", () => {
    vi.spyOn(systemExtras, "useTasks").mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: { message: "system tasks unreachable" },
    } as unknown as ReturnType<typeof systemExtras.useTasks>);
    _stubTrigger();

    renderWithProviders(<TasksTab />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Tasks unavailable")).toBeInTheDocument();
    expect(screen.getByText("system tasks unreachable")).toBeInTheDocument();
  });

  it("renders one row per job and fires Run-now → useTriggerCommand", () => {
    vi.spyOn(systemExtras, "useTasks").mockReturnValue({
      data: [
        {
          id: "MissingSearch",
          name: "Missing Search",
          schedule_cron: "0 */6 * * *",
          schedule_interval_seconds: null,
          last_run_at: null,
          last_run_status: "success",
          last_error: null,
          next_run_at: null,
          enabled: true,
        },
        {
          id: "DisabledJob",
          name: "Disabled Job",
          schedule_cron: null,
          schedule_interval_seconds: 30,
          last_run_at: null,
          last_run_status: null,
          last_error: null,
          next_run_at: null,
          enabled: false,
        },
      ],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof systemExtras.useTasks>);
    const mutate = _stubTrigger();

    renderWithProviders(<TasksTab />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Missing Search")).toBeInTheDocument();
    expect(screen.getByText("Disabled Job")).toBeInTheDocument();
    // The success status badge for the enabled job.
    expect(screen.getByText("success")).toBeInTheDocument();

    // Only ONE Run-now button (the enabled job has it; disabled
    // job hides it).
    const runButtons = screen.getAllByRole("button", { name: "Run now" });
    expect(runButtons).toHaveLength(1);

    fireEvent.click(runButtons[0]!);
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0]?.[0]).toEqual({ name: "MissingSearch" });
  });
});
