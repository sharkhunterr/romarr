import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { DatVerifiedBadge } from "./DatVerifiedBadge";

describe("DatVerifiedBadge", () => {
  it("renders an emerald icon when verified", () => {
    const { container } = render(<DatVerifiedBadge status="verified" />);
    const badge = container.querySelector("span")!;
    expect(badge.className).toContain("emerald");
    expect(badge.querySelector("svg")).not.toBeNull();
  });

  it("renders an amber icon when invalid (BADDUMP/HACK)", () => {
    const { container } = render(<DatVerifiedBadge status="invalid" />);
    const badge = container.querySelector("span")!;
    expect(badge.className).toContain("amber");
    expect(badge.getAttribute("title")).toContain("BADDUMP");
  });

  it("renders a zinc icon when status is unknown", () => {
    const { container } = render(<DatVerifiedBadge status="unknown" />);
    const badge = container.querySelector("span")!;
    expect(badge.className).toContain("zinc");
    expect(badge.getAttribute("title")).toContain("not found");
  });

  it("renders nothing when status is absent", () => {
    const { container } = render(<DatVerifiedBadge status="absent" />);
    expect(container.firstChild).toBeNull();
  });

  it("accepts a custom title override", () => {
    const { container } = render(
      <DatVerifiedBadge status="verified" title="Specific tooltip" />,
    );
    expect(container.querySelector("span")!.getAttribute("title")).toBe(
      "Specific tooltip",
    );
  });
});
