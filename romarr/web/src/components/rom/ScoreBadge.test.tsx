import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ScoreBadge } from "./ScoreBadge";

describe("ScoreBadge", () => {
  it("renders a positive score with leading +", () => {
    const { container } = render(<ScoreBadge score={50} />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("+50");
    expect(badge.className).toContain("emerald");
  });

  it("renders zero as positive (still emerald, with leading +)", () => {
    const { container } = render(<ScoreBadge score={0} />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("+0");
    expect(badge.className).toContain("emerald");
  });

  it("renders a negative score in red without a manual sign", () => {
    const { container } = render(<ScoreBadge score={-25} />);

    const badge = container.querySelector("span")!;
    expect(badge).toHaveTextContent("-25");
    expect(badge.className).toContain("red");
  });

  it("formats the breakdown as a multi-line title attribute", () => {
    const { container } = render(
      <ScoreBadge
        score={75}
        breakdown={[
          { format: "x264", contribution: 100 },
          { format: "Repack", contribution: -25 },
        ]}
      />,
    );

    const badge = container.querySelector("span")!;
    const title = badge.getAttribute("title");
    expect(title).toContain("x264: +100");
    expect(title).toContain("Repack: -25");
  });

  it("omits the title when no breakdown is supplied", () => {
    const { container } = render(<ScoreBadge score={10} />);

    const badge = container.querySelector("span")!;
    expect(badge.getAttribute("title")).toBeNull();
  });
});
