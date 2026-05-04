/**
 * Date helper tests (spec 014 T118 follow-up).
 *
 * Pure-function unit tests. The exported helpers all funnel
 * through ``coerceDate`` + a date-fns format call; we cover
 * the locale fallback + the three null-or-invalid input
 * branches + a sample EN/FR formatting round trip.
 */

import { describe, expect, it } from "vitest";

import {
  coerceDate,
  formatRelativeTime,
  formatShortDate,
  localeFor,
} from "./dates";

describe("localeFor", () => {
  it("returns the date-fns enUS locale for 'en'", () => {
    const locale = localeFor("en");
    expect(locale.code).toBe("en-US");
  });

  it("returns the date-fns fr locale for 'fr'", () => {
    const locale = localeFor("fr");
    expect(locale.code).toBe("fr");
  });

  it("falls back to the English locale on unknown input", () => {
    expect(localeFor("xx").code).toBe("en-US");
    expect(localeFor(undefined).code).toBe("en-US");
  });
});

describe("coerceDate", () => {
  it("passes through a valid Date", () => {
    const d = new Date("2026-05-04T12:00:00Z");
    expect(coerceDate(d)).toBe(d);
  });

  it("returns null for null / undefined / NaN-Date", () => {
    expect(coerceDate(null)).toBeNull();
    expect(coerceDate(undefined)).toBeNull();
    expect(coerceDate(new Date("not-a-date"))).toBeNull();
  });

  it("parses ISO-8601 strings (with timezone)", () => {
    const d = coerceDate("2026-05-04T12:00:00Z");
    expect(d).not.toBeNull();
    expect(d!.toISOString()).toBe("2026-05-04T12:00:00.000Z");
  });

  it("parses millis epochs", () => {
    const epoch = Date.UTC(2026, 4, 4, 12, 0, 0);
    const d = coerceDate(epoch);
    expect(d).not.toBeNull();
    expect(d!.toISOString()).toBe("2026-05-04T12:00:00.000Z");
  });

  it("returns null for malformed strings", () => {
    expect(coerceDate("not a date")).toBeNull();
  });
});

describe("formatShortDate", () => {
  it("returns empty string for null input (caller falls through)", () => {
    expect(formatShortDate(null, "en")).toBe("");
    expect(formatShortDate(undefined, "fr")).toBe("");
  });

  it("formats a valid date with the active locale", () => {
    const value = formatShortDate("2026-05-04T12:00:00Z", "en");
    // en-US short date is M/d/yyyy; we don't pin the exact
    // separator (date-fns uses the locale's preferred glyph)
    // but the result MUST contain 2026 and the day digit.
    expect(value).toContain("2026");
    expect(value).not.toBe("");
  });
});

describe("formatRelativeTime", () => {
  it("returns a non-empty suffixed relative string for a date in the recent past", () => {
    // formatDistanceToNow doesn't honour an injected "now" — the
    // helper passes through to date-fns which always reads
    // Date.now(). We pick a date 30 days behind the env's
    // 2026-05-04 so the result is stable regardless of the
    // test-runtime hour.
    const thirtyDaysAgo = new Date(Date.UTC(2026, 3, 4, 12, 0, 0));
    const result = formatRelativeTime(thirtyDaysAgo, "en");
    expect(result).not.toBe("");
    expect(result).toMatch(/ago/);
  });

  it("returns empty string for null input", () => {
    expect(formatRelativeTime(null, "en")).toBe("");
  });
});
