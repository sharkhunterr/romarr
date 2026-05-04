/**
 * eventToInvalidations test (spec 014 T046).
 *
 * Pure-function unit test: each documented MessageType maps
 * to the documented query-key list. Verified one branch per
 * message type so a future addition to the switch statement
 * shows up loudly.
 */

import { describe, expect, it } from "vitest";

import { eventToInvalidations } from "./invalidations";

describe("eventToInvalidations", () => {
  it("invalidates system/tasks + history for the three task lifecycle messages", () => {
    for (const m of ["taskStarted", "taskProgress", "taskFinished"] as const) {
      expect(eventToInvalidations(m)).toEqual([
        ["system", "tasks"],
        ["history"],
      ]);
    }
  });

  it("invalidates queue for queueUpdated", () => {
    expect(eventToInvalidations("queueUpdated")).toEqual([["queue"]]);
  });

  it("invalidates games + wanted + library for the three game lifecycle messages", () => {
    for (const m of ["gameAdded", "gameUpdated", "gameDeleted"] as const) {
      expect(eventToInvalidations(m)).toEqual([
        ["games"],
        ["wanted"],
        ["library"],
      ]);
    }
  });

  it("invalidates wanted + history + queue for the three release acquisition messages", () => {
    for (const m of [
      "releaseGrabbed",
      "releaseImported",
      "releaseFailed",
    ] as const) {
      expect(eventToInvalidations(m)).toEqual([
        ["wanted"],
        ["history"],
        ["queue"],
      ]);
    }
  });

  it("invalidates system/health for healthChanged", () => {
    expect(eventToInvalidations("healthChanged")).toEqual([
      ["system", "health"],
    ]);
  });

  it("returns no invalidations for systemMessage (toast-only)", () => {
    expect(eventToInvalidations("systemMessage")).toEqual([]);
  });
});
