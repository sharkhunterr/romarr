import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { DatVerifiedBadge } from "./DatVerifiedBadge";

describe("DatVerifiedBadge", () => {
  it("renders a green ✓ badge when verified", () => {
    const { container } = render(<DatVerifiedBadge verified />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("DAT");
    expect(badge).toHaveTextContent("✓");
    expect(badge.className).toContain("emerald");
  });

  it("renders a dimmed ? badge when not verified", () => {
    const { container } = render(<DatVerifiedBadge verified={false} />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("DAT");
    expect(badge).toHaveTextContent("?");
    expect(badge.className).toContain("zinc");
  });

  it("includes the source name in the verified tooltip", () => {
    const { container } = render(
      <DatVerifiedBadge verified source="No-Intro 2026-04" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toBe("Verified against No-Intro 2026-04");
  });

  it("uses the bare 'Verified' tooltip when source is omitted", () => {
    const { container } = render(<DatVerifiedBadge verified />);

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toBe("Verified");
  });

  it("uses the no-match tooltip when not verified", () => {
    const { container } = render(<DatVerifiedBadge verified={false} />);

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toContain("No DAT match");
  });
});
