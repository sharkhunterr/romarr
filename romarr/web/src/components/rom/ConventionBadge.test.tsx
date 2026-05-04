import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { ConventionBadge } from "./ConventionBadge";

describe("ConventionBadge", () => {
  it("renders the No-Intro label with emerald styling", () => {
    const { container } = render(<ConventionBadge convention="no-intro" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("No-Intro");
    expect(badge.className).toContain("emerald");
  });

  it("renders Redump in sky blue", () => {
    const { container } = render(<ConventionBadge convention="redump" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("Redump");
    expect(badge.className).toContain("sky");
  });

  it("renders TOSEC in neutral grey", () => {
    const { container } = render(<ConventionBadge convention="tosec" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("TOSEC");
    expect(badge.className).toContain("zinc");
  });

  it("renders GoodTools in amber", () => {
    const { container } = render(<ConventionBadge convention="goodtools" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("GoodTools");
    expect(badge.className).toContain("amber");
  });

  it("renders Scene in purple", () => {
    const { container } = render(<ConventionBadge convention="scene" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("Scene");
    expect(badge.className).toContain("purple");
  });

  it("renders Unknown as the dimmed fallback", () => {
    const { container } = render(<ConventionBadge convention="unknown" />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("Unknown");
    expect(badge.className).toContain("zinc");
  });

  it("applies operator-supplied className alongside base classes", () => {
    const { container } = render(
      <ConventionBadge convention="no-intro" className="my-custom" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge.className).toContain("my-custom");
    expect(badge.className).toContain("rounded-full");
  });
});
