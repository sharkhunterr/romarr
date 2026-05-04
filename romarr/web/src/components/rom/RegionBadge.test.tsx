/**
 * RegionBadge component test.
 *
 * Doubles as the smoke-test that the spec 014 vitest infra works:
 * jsdom + jest-dom matchers + render-and-query are wired and a
 * trivial component renders + asserts as expected. Future
 * spec 014 component tests follow this shape.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { RegionBadge } from "./RegionBadge";

describe("RegionBadge", () => {
  it("renders the documented flag for a known region", () => {
    render(<RegionBadge code="USA" />);

    const badge = screen.getByLabelText("Region USA");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("USA");
    expect(badge).toHaveTextContent("🇺🇸");
  });

  it("normalises lowercase region codes to uppercase", () => {
    render(<RegionBadge code="jpn" />);

    expect(screen.getByLabelText("Region JPN")).toBeInTheDocument();
    expect(screen.getByText("JPN")).toBeInTheDocument();
  });

  it("falls back to a neutral flag for unknown codes", () => {
    render(<RegionBadge code="MARS" />);

    const badge = screen.getByLabelText("Region MARS");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("MARS");
    // White flag emoji is the documented fallback per the
    // component's source.
    expect(badge).toHaveTextContent("🏳️");
  });

  it("applies the operator-supplied className alongside the base classes", () => {
    const { container } = render(
      <RegionBadge code="USA" className="my-custom" />,
    );

    const badge = container.querySelector("span[aria-label='Region USA']")!;
    expect(badge.className).toContain("my-custom");
    // Base utility classes still applied.
    expect(badge.className).toContain("inline-flex");
  });
});
