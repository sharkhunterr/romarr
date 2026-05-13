import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { DatVerifiedBadge } from "./DatVerifiedBadge";

describe("DatVerifiedBadge", () => {
  it("renders a green ✓ badge when verified against a source", () => {
    const { container } = render(
      <DatVerifiedBadge verified source="no-intro" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("DAT");
    expect(badge).toHaveTextContent("✓");
    expect(badge.className).toContain("emerald");
  });

  it("renders an amber ! badge when matched but unverified", () => {
    const { container } = render(
      <DatVerifiedBadge verified={false} source="no-intro" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("DAT");
    expect(badge).toHaveTextContent("!");
    expect(badge.className).toContain("amber");
  });

  it("renders nothing when no DAT source matched the hash", () => {
    const { container } = render(<DatVerifiedBadge verified={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when source is explicitly null", () => {
    const { container } = render(
      <DatVerifiedBadge verified={false} source={null} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("includes the source name in the verified tooltip", () => {
    const { container } = render(
      <DatVerifiedBadge verified source="No-Intro 2026-04" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toBe(
      "Verified against No-Intro 2026-04",
    );
  });

  it("flags BADDUMP/HACK in the warning tooltip", () => {
    const { container } = render(
      <DatVerifiedBadge verified={false} source="no-intro" />,
    );

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toContain("BADDUMP");
  });
});
