/**
 * HistoryTimeline — session-grouping behaviour.
 *
 * The 30-minute gap heuristic is the heart of the per-game
 * timeline view: events whose timestamps are closer than that
 * collapse into one session block; events further apart open a
 * new session header. A regression here would either lump every
 * day's worth of activity into a single block (useless wall) or
 * fragment every single event into its own session (no chain
 * surfaced).
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { HistoryTimeline } from "./HistoryTimeline";

// Minimal shape — only the fields the timeline reads.
function fakeEvent(
  id: number,
  date: string,
  eventType: "import" | "search" = "import",
): {
  id: number;
  date: string;
  eventType: string;
  successful: boolean;
  gameId: number;
} {
  return {
    id,
    date,
    eventType,
    successful: true,
    gameId: 1,
  };
}

function renderTimeline(events: ReturnType<typeof fakeEvent>[]): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <HistoryTimeline
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        events={events as any}
        locale="en-US"
        i18nNs="game"
      />
    </MemoryRouter>,
  );
}

describe("HistoryTimeline session grouping", () => {
  it("collapses events <30 min apart into one session", () => {
    // Three imports landing within ten minutes of each other —
    // the search → grab → import chain shape we care about.
    renderTimeline([
      fakeEvent(3, "2026-05-26T15:10:00Z", "import"),
      fakeEvent(2, "2026-05-26T15:05:00Z", "search"),
      fakeEvent(1, "2026-05-26T15:00:00Z", "search"),
    ]);
    // Only one session header is rendered (sections with the
    // ``Activity session`` accessible name).
    const sections = screen.getAllByRole("region");
    expect(sections).toHaveLength(1);
  });

  it("splits into separate sessions when gap exceeds 30 min", () => {
    renderTimeline([
      // Newest — own session.
      fakeEvent(3, "2026-05-26T15:00:00Z", "import"),
      // Old — own session, ~3h before.
      fakeEvent(2, "2026-05-26T12:00:00Z", "search"),
      // Very old — collapses with #2 (5 min before).
      fakeEvent(1, "2026-05-26T11:55:00Z", "search"),
    ]);
    const sections = screen.getAllByRole("region");
    expect(sections).toHaveLength(2);
  });

  it("renders nothing when given an empty event list", () => {
    const { container } = renderTimeline([]);
    expect(container.querySelectorAll("[role='region']")).toHaveLength(0);
  });
});
