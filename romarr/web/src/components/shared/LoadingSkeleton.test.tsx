import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import {
  CardGridSkeleton,
  DetailSkeleton,
  ListSkeleton,
  Skeleton,
} from "./LoadingSkeleton";

describe("Skeleton primitives", () => {
  it("Skeleton applies the shimmer base class plus the operator className", () => {
    const { container } = render(<Skeleton className="my-custom h-4" />);

    const div = container.querySelector("div")!;
    expect(div.className).toContain("animate-pulse");
    expect(div.className).toContain("my-custom");
    expect(div.className).toContain("h-4");
    // Decorative — hidden from assistive tech.
    expect(div.getAttribute("aria-hidden")).toBe("true");
  });

  it("ListSkeleton renders the documented default of 6 rows", () => {
    const { container } = render(<ListSkeleton />);

    const items = container.querySelectorAll("ul > li");
    expect(items.length).toBe(6);
  });

  it("ListSkeleton honours the operator-supplied row count", () => {
    const { container } = render(<ListSkeleton rows={3} />);

    expect(container.querySelectorAll("ul > li").length).toBe(3);
  });

  it("CardGridSkeleton renders the default 8 cards", () => {
    const { container } = render(<CardGridSkeleton />);

    // Each card is a top-level <div> inside the grid container.
    const grid = container.querySelector(".grid")!;
    expect(grid.children.length).toBe(8);
  });

  it("CardGridSkeleton honours the operator-supplied card count", () => {
    const { container } = render(<CardGridSkeleton cards={4} />);

    const grid = container.querySelector(".grid")!;
    expect(grid.children.length).toBe(4);
  });

  it("DetailSkeleton renders the documented header layout", () => {
    const { container } = render(<DetailSkeleton />);

    // Cover skeleton + 4 meta rows = 5 inner shimmer divs.
    const shimmers = container.querySelectorAll(".animate-pulse");
    expect(shimmers.length).toBe(5);
  });
});
